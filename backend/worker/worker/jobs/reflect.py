from __future__ import annotations

import logging
import uuid

from core.intelligence.call_types import CallType
from core.intelligence.prompts import reflect as reflect_prompt
from core.models.observability import ProceduralKnowledgeLog, SkillSnapshot
from core.models.tasks import Task, TaskExecution
from core.models.agents import Agent
from worker.context import get_worker_context
from worker.span import JobSpan

logger = logging.getLogger(__name__)


async def reflect(
    ctx: dict,
    agent_id: str,
    task_id: str,
    workspace_id: str,
    execution_id: str,
    quality_score: float,
) -> None:
    """Post-execution reflection — enqueued by ReflectJobHandler after a self-execute path.

    Extracts skill deltas and a generalised procedural rule from the completed execution.
    Full reflection (rule extraction + supersession check) only runs when the task was
    non-trivial: difficulty >= 3 or more than 3 graph steps.
    """
    async with JobSpan(
        uuid.UUID(agent_id), uuid.UUID(task_id), uuid.UUID(workspace_id)
    ) as span:
        async with span.session() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            agent = await session.get(Agent, uuid.UUID(agent_id))
            execution = await session.get(TaskExecution, uuid.UUID(execution_id))

        if not task or not agent or not execution:
            logger.warning(
                "reflect: missing records — task=%s agent=%s execution=%s",
                task_id, agent_id, execution_id,
            )
            return

        wctx = get_worker_context()
        step_count = len(execution.tool_trace) if execution.tool_trace else 0
        full_reflect = (task.difficulty or 1.0) >= 3.0 or step_count > 3

        await span.emit("agent.reflecting", {"full_reflect": full_reflect})

        existing_rules: list[dict] = []
        if full_reflect and task.task_type:
            items = await wctx.memory.retrieve_procedures_for_domain(
                agent_id, workspace_id, task.task_type
            )
            existing_rules = [
                {
                    "id":     item.id,
                    "domain": (item.payload or {}).get("domain", ""),
                    "text":   item.text,
                }
                for item in items
            ]

        task_ctx = {
            "title":           task.title,
            "description":     task.description,
            "task_type":       task.task_type,
            "required_skills": task.required_skills or {},
            "difficulty":      task.difficulty,
        }
        result_ctx = {
            "summary":    execution.artifact_uri or "",
            "tool_trace": execution.tool_trace or [],
        }

        raw = await wctx.llm_router.complete(
            reflect_prompt.build_prompt(
                task_ctx,
                result_ctx,
                quality_score,
                existing_rules=existing_rules if full_reflect else None,
            ),
            CallType.REFLECT,
            json_mode=True,
        )
        response = reflect_prompt.parse(raw)

        async with span.session() as session:
            if response.skill_deltas:
                merged = {
                    k: max(0.0, min(1.0, (agent.skills or {}).get(k, 0.0) + delta))
                    for k, delta in response.skill_deltas.items()
                }
                agent.skills = {**(agent.skills or {}), **merged}
                session.add(agent)
                session.add(SkillSnapshot(
                    agent_id=agent.id,
                    organisation_id=agent.organisation_id,
                    workspace_id=agent.workspace_id,
                    skills=agent.skills,
                ))

            if full_reflect and response.generalised_rule:
                session.add(ProceduralKnowledgeLog(
                    workspace_id=task.workspace_id,
                    agent_id=agent.id,
                    domain=task.task_type or "general",
                    rule_text=response.generalised_rule,
                ))

        if full_reflect and response.generalised_rule:
            await wctx.memory.store_procedure(
                agent_id,
                workspace_id,
                rule=response.generalised_rule,
                domain=task.task_type or "general",
                verdict=response.verdict,
                superseded_ids=response.superseded_ids,
            )

        await span.emit("job.completed", {})
        logger.info(
            "reflect: agent=%s task=%s full_reflect=%s skill_deltas=%s",
            agent_id, task_id, full_reflect,
            list(response.skill_deltas.keys()) if response.skill_deltas else [],
        )
