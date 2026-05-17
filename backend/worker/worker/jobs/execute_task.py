from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload

from core.agents.agent import build_initial_state
from core.agents.graphs.state import GraphState
from core.agents.scoring import score_outcome
from core.coordination.contract_net import issue_cfp
from core.coordination.decompose import decompose_and_publish
from core.coordination.task_state import TaskStateMachine
from core.intelligence.call_types import CallType
from core.intelligence.prompts import decompose as decompose_prompt
from core.intelligence.prompts import evaluate
from core.models.agents import Agent
from core.models.observability import InfluenceSnapshot, SkillSnapshot
from core.models.tasks import Task, TaskExecution
from worker.context import get_worker_context
from worker.span import JobSpan

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def execute_task(
    ctx: dict,
    agent_id: str,
    task_id: str,
    workspace_id: str,
) -> None:
    """Main execution job. Three-phase transaction structure.

    Phase 1 (read) — load Agent + Task; session closes before graph runs.
    Phase 2 (write execution row) — create TaskExecution with status "executing".
    Phase 3 (write results) — single atomic commit for execution, agent, snapshots, task.
    """
    async with JobSpan(
        uuid.UUID(agent_id), uuid.UUID(task_id), uuid.UUID(workspace_id)
    ) as span:

        # ── Phase 1: READ ──────────────────────────────────────────────────────
        async with span.session() as session:
            agent = await session.get(
                Agent, uuid.UUID(agent_id),
                options=[selectinload(Agent.task_executions)],
            )
            task = await session.get(
                Task, uuid.UUID(task_id),
                options=[selectinload(Task.subtasks)],
            )
            if agent is None or task is None:
                logger.warning(
                    "execute_task: agent=%s or task=%s not found — skipping",
                    agent_id, task_id,
                )
                return

        wctx = get_worker_context()

        # ── Phase 2: WRITE EXECUTION ROW ───────────────────────────────────────
        execution = TaskExecution(
            task_id=task.id,
            agent_id=agent.id,
            organisation_id=agent.organisation_id,
            workspace_id=task.workspace_id,
            status="executing",
            started_at=datetime.now(timezone.utc),
        )
        async with span.session() as session:
            session.add(execution)
            TaskStateMachine.transition(task, "executing")
            session.add(task)

        await span.emit("job.started", {"task_type": task.task_type})

        # ── Phase 3: LLM EVALUATE ──────────────────────────────────────────────
        await span.emit("agent.evaluating", {})
        agent_ctx = {
            "name":      agent.name,
            "skills":    agent.skills or {},
            "influence": agent.influence or 0.0,
        }
        task_ctx = {
            "title":           task.title,
            "description":     task.description,
            "required_skills": task.required_skills or {},
            "difficulty":      task.difficulty,
            "domain_tags":     task.domain_tags or {},
            "task_type":       task.task_type,
        }

        raw = await wctx.llm_router.complete(
            evaluate.build_prompt(agent_ctx, task_ctx),
            CallType.EVALUATE,
            json_mode=True,
        )
        decision = evaluate.parse(raw)

        # ── Phase 4: ACT ON DECISION ───────────────────────────────────────────
        if decision.decision == "decompose":
            await span.emit("agent.decomposing", {"reasoning": decision.reasoning})
            raw_decompose = await wctx.llm_router.complete(
                decompose_prompt.build_prompt(agent_ctx, task_ctx),
                CallType.DECOMPOSE,
                json_mode=True,
            )
            decompose_resp = decompose_prompt.parse(raw_decompose)
            specs = [s.model_dump() for s in decompose_resp.subtasks]

            async with span.session() as session:
                await decompose_and_publish(agent, task, specs, session, wctx.bus)

            await _finalise_execution(span, execution, task, "completed")
            return

        if decision.decision == "cfp":
            await span.emit("agent.issuing_cfp", {"reasoning": decision.reasoning})
            await issue_cfp(task, agent, wctx.bus)
            await _finalise_execution(span, execution, task, "completed")
            return

        # ── Phase 5: SELF-EXECUTE via LangGraph ────────────────────────────────
        # No open DB session during graph execution — connections are a scarce resource.
        await span.emit("agent.executing", {})
        initial_state = build_initial_state(agent, task)
        final_state: GraphState = await wctx.graphs[task.task_type or "general"].ainvoke(
            initial_state
        )

        quality = score_outcome(task, final_state)
        await span.emit("agent.scored", {"quality_score": quality})

        # ── Phase 6: WRITE RESULTS (single atomic commit) ──────────────────────
        async with span.session() as session:
            execution.status        = "completed"
            execution.quality_score = quality
            execution.artifact_uri  = final_state.get("artifact")
            execution.tool_trace    = span.events
            execution.completed_at  = datetime.now(timezone.utc)
            session.add(execution)

            new_skills    = _merge_skills(agent.skills, final_state)
            new_influence = _update_influence(agent.influence, quality)
            agent.skills     = new_skills
            agent.influence  = new_influence
            agent.updated_at = datetime.now(timezone.utc)
            session.add(agent)

            session.add(SkillSnapshot(
                agent_id=agent.id,
                organisation_id=agent.organisation_id,
                workspace_id=agent.workspace_id,
                skills=new_skills,
            ))
            session.add(InfluenceSnapshot(
                agent_id=agent.id,
                organisation_id=agent.organisation_id,
                workspace_id=agent.workspace_id,
                influence=new_influence,
            ))

            TaskStateMachine.transition(task, "completed")
            session.add(task)

        # ── Phase 7: MEMORY + DOWNSTREAM EVENTS ───────────────────────────────
        await wctx.memory.store_episode(
            agent_id,
            workspace_id,
            {
                "text":         f"Completed task: {task.title}. Quality: {quality:.2f}.",
                "task_id":      task_id,
                "task_type":    task.task_type,
                "quality_score": quality,
                "artifact":     final_state.get("artifact"),
            },
        )

        await wctx.bus.publish(
            "stream:task",
            {
                "event_type":          "task.completed",
                "task_id":             task_id,
                "workspace_id":        workspace_id,
                "completing_agent_id": agent_id,
                "quality_score":       quality,
                "task_type":           task.task_type,
            },
        )

        await span.emit("job.completed", {"quality_score": quality})

        await wctx.arq_queue.enqueue_job(
            "reflect",
            agent_id=agent_id,
            task_id=task_id,
            workspace_id=workspace_id,
            execution_id=str(execution.id),
            quality_score=quality,
            step_count=final_state["step_count"],
        )

        logger.info(
            "execute_task: agent=%s task=%s quality=%.3f",
            agent_id, task_id, quality,
        )


async def _finalise_execution(
    span: JobSpan,
    execution: TaskExecution,
    task: Task,
    status: str,
) -> None:
    """Write final status for decompose/cfp paths (no graph execution, no quality score)."""
    async with span.session() as session:
        execution.status       = status
        execution.completed_at = datetime.now(timezone.utc)
        execution.tool_trace   = span.events
        session.add(execution)
        TaskStateMachine.transition(task, "completed")
        session.add(task)

    await span.emit("job.completed", {"path": "delegated"})


def _merge_skills(
    current_skills: dict[str, float] | None,
    final_state: GraphState,
) -> dict[str, float]:
    """Carry existing skills forward — reflect job applies the deltas after LLM reflection."""
    return dict(current_skills or {})


def _update_influence(current: float | None, quality: float) -> float:
    """Blend quality into the running influence score via EMA."""
    from core.config import settings
    base = current if current is not None else 0.0
    return base + settings.INFLUENCE_EMA_ALPHA * (quality - base)
