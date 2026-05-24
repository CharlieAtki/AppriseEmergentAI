from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload

from core.eventing.activity.task_logger import TaskActivityLogger
from core.agents.agent import build_initial_state
from core.agents.graphs.state import GraphState
from core.agents.scoring import score_outcome
from core.coordination.contract_net import issue_cfp
from core.coordination.decompose import decompose_and_publish
from core.coordination.task_context import MAX_DELEGATION_DEPTH, TaskContext
from core.coordination.task_state import TaskStateMachine
from core.eventing.events.task_events import TaskSnapshot
from core.intelligence.call_types import CallType
from core.intelligence.prompts import decompose as decompose_prompt
from core.intelligence.prompts import evaluate
from core.intelligence.prompts.evaluate import EvaluateResponse
from core.models.agents import Agent
from core.models.observability import SkillSnapshot
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
    """Main execution job.

    Phase 1 (read)            — load Agent + Task; session closes before any mutation.
    Phase 2 (write exec row)  — create TaskExecution("executing"), task → "executing".
    Phase 3 (LLM evaluate)    — decide: decompose / cfp / self-execute.
    Phase 4 (act)             — branch on decision.
    Phase 5 (self-execute)    — LangGraph graph; no open DB session.
    Phase 6 (write results)   — single atomic commit for execution, agent, snapshots, task.
    Phase 7 (events)          — memory write, bus events, reflect job enqueue.

    On any exception after Phase 2 commits: the except block writes task → "failed" and
    execution → "failed" so the row is not left dangling. Re-raises for ARQ to record.
    On retry: the terminal-state guard in Phase 1 returns early — retries are idempotent.
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

        # Guard: if this is a retry and the previous attempt already wrote a terminal
        # status, do not re-execute. The state machine would reject the transition anyway.
        if TaskStateMachine.is_terminal(task.status):
            logger.info(
                "execute_task: task=%s already terminal (%s) — skipping retry",
                task_id, task.status,
            )
            return

        # Build provenance context while task attributes are in-memory.
        # expire_on_commit=False on SessionLocal keeps scalar attrs after session close.
        provenance = TaskContext.from_task(task)
        depth_exceeded = provenance.delegation_depth >= MAX_DELEGATION_DEPTH

        wctx = get_worker_context()
        task_logger = TaskActivityLogger(wctx.event_bus.apublish)
        execution: TaskExecution | None = None
        # Tracks the task status as last committed to DB. In-memory task.status
        # can diverge from the DB if a session raises after the ORM mutation but
        # before commit. The failure path uses this to avoid skipping cleanup when
        # the DB row is still at "executing" but task.status in-memory shows a later value.
        committed_task_status = task.status

        try:
            # ── Phase 2: WRITE EXECUTION ROW ───────────────────────────────────
            execution = TaskExecution(
                task_id=task.id,
                agent_id=agent.id,
                organisation_id=agent.organisation_id,
                workspace_id=task.workspace_id,
                status="executing",
                started_at=datetime.now(timezone.utc),
            )
            before_executing = TaskSnapshot.from_domain(task, executing_agent_id=agent.id)
            async with span.session() as session:
                session.add(execution)
                TaskStateMachine.transition(task, "executing")
                session.add(task)
            committed_task_status = task.status  # "executing"
            await task_logger.updated(before_executing, task, executing_agent_id=agent.id)

            await span.emit("job.started", {"task_type": task.task_type})

            # ── Phase 3: LLM EVALUATE ────────────────────────────────────────────
            await span.emit("agent.evaluating", {})
            agent_ctx = {
                "name":      agent.name,
                "skills":    agent.skills or {},
                "influence": agent.influence or 0.0,
            }
            task_ctx = {
                "title":            task.title,
                "description":      task.description,
                "required_skills":  task.required_skills or {},
                "difficulty":       task.difficulty,
                "domain_tags":      task.domain_tags or {},
                "task_type":        task.task_type,
                "delegation_depth": provenance.delegation_depth,
                "depth_exceeded":   depth_exceeded,
            }

            raw = await wctx.llm_router.complete(
                evaluate.build_prompt(agent_ctx, task_ctx),
                CallType.EVALUATE,
                json_mode=True,
            )
            decision = evaluate.parse(raw)

            if depth_exceeded and decision.decision != "self_execute":
                logger.warning(
                    "execute_task: depth guard forcing self_execute for task=%s (depth=%d)",
                    task.id, provenance.delegation_depth,
                )
                decision = EvaluateResponse(decision="self_execute", reasoning="depth guard")

            # ── Phase 4: ACT ON DECISION ─────────────────────────────────────────
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
                    await decompose_and_publish(
                        agent, task, specs, session, wctx.bus,
                        task_ctx=provenance,
                        task_logger=task_logger,
                    )

                await _finalise_execution(span, execution, task, "completed", task_logger, execution_path="decompose")
                return

            if decision.decision == "cfp":
                await span.emit("agent.issuing_cfp", {"reasoning": decision.reasoning})
                await issue_cfp(task, agent, wctx.bus)
                await _release_to_pool(span, execution, task, task_id, workspace_id, wctx, task_logger)
                return

            # ── Phase 5: SELF-EXECUTE via LangGraph ──────────────────────────────
            # No open DB session during graph execution — connections are a scarce resource.
            await span.emit("agent.executing", {})
            initial_state = build_initial_state(agent, task)
            final_state: GraphState = await wctx.graphs[task.task_type or "general"].ainvoke(
                initial_state
            )

            quality = score_outcome(task, final_state)
            await span.emit("agent.scored", {"quality_score": quality})

            # ── Phase 6: WRITE RESULTS (single atomic commit) ────────────────────
            before_completed = TaskSnapshot.from_domain(task, executing_agent_id=agent.id)
            async with span.session() as session:
                execution.status        = "completed"
                execution.quality_score = quality
                execution.artifact_uri  = final_state.get("artifact")
                execution.tool_trace    = final_state["tool_trace"]   # structured {tool,args,result} records
                execution.completed_at  = datetime.now(timezone.utc)
                session.add(execution)

                new_skills       = _merge_skills(agent.skills, final_state)
                agent.skills     = new_skills
                agent.updated_at = datetime.now(timezone.utc)
                session.add(agent)

                session.add(SkillSnapshot(
                    agent_id=agent.id,
                    organisation_id=agent.organisation_id,
                    workspace_id=agent.workspace_id,
                    skills=new_skills,
                ))

                TaskStateMachine.transition(task, "completed")
                session.add(task)

            await task_logger.updated(
                before_completed, task,
                executing_agent_id=agent.id,
                quality_score=quality,
                execution_id=execution.id,
                execution_path="self_execute",
            )

            # ── Phase 7: DOWNSTREAM EVENTS ───────────────────────────────────────
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

            logger.info(
                "execute_task: agent=%s task=%s quality=%.3f",
                agent_id, task_id, quality,
            )

        except BaseException as exc:
            # Write failure state so the task and execution rows are not left dangling.
            # The session that failed has already rolled back; open a fresh one.
            # execution may be None if Phase 2 never committed (its session rolled back,
            # leaving the task at "reserved" — safe to skip the execution update in that case).
            logger.exception(
                "execute_task failed: agent=%s task=%s", agent_id, task_id
            )
            before_failed: TaskSnapshot | None = None
            try:
                async with span.session() as session:
                    if execution is not None:
                        execution.status       = "failed"
                        execution.completed_at = datetime.now(timezone.utc)
                        execution.error        = {
                            "type":    type(exc).__name__,
                            "message": str(exc),
                        }
                        session.add(execution)
                    if not TaskStateMachine.is_terminal(committed_task_status):
                        task.status = committed_task_status  # reset in-memory to last committed value
                        before_failed = TaskSnapshot.from_domain(task)
                        TaskStateMachine.transition(task, "failed")
                        session.add(task)
                if before_failed is not None:
                    await task_logger.updated(before_failed, task)
            except Exception:
                logger.exception(
                    "execute_task: could not write failure state for task=%s", task_id
                )
            raise


async def _release_to_pool(
    span: JobSpan,
    execution: TaskExecution,
    task: Task,
    task_id: str,
    workspace_id: str,
    wctx,
    task_logger: TaskActivityLogger,
) -> None:
    """CFP path: agent decided to delegate — mark execution done, release task back to pool.

    The executing agent's decision job is complete (execution → "completed"), but the
    task itself was never worked on, so it returns to "open" for re-bidding. The Redis
    reservation key is deleted immediately so the next winner isn't blocked by TTL.
    """
    before = TaskSnapshot.from_domain(task, executing_agent_id=execution.agent_id)
    async with span.session() as session:
        execution.status       = "completed"
        execution.completed_at = datetime.now(timezone.utc)
        execution.tool_trace   = span.events
        session.add(execution)
        TaskStateMachine.transition(task, "open")
        session.add(task)
    await task_logger.updated(before, task, executing_agent_id=execution.agent_id, execution_path="cfp")

    await wctx.redis.delete(f"reservation:{workspace_id}:{task_id}")

    await wctx.bus.publish(
        "stream:task",
        {
            "event_type":      "task.created",
            "task_id":         task_id,
            "workspace_id":    workspace_id,
            "required_skills": task.required_skills or {},
            "domain_tags":     task.domain_tags or {},
        },
    )

    await span.emit("job.completed", {"path": "cfp_released"})


async def _finalise_execution(
    span: JobSpan,
    execution: TaskExecution,
    task: Task,
    status: str,
    task_logger: TaskActivityLogger,
    *,
    execution_path: str,
) -> None:
    """Write final status for decompose/cfp paths (no graph execution, no quality score)."""
    before = TaskSnapshot.from_domain(task, executing_agent_id=execution.agent_id)
    async with span.session() as session:
        execution.status       = status
        execution.completed_at = datetime.now(timezone.utc)
        execution.tool_trace   = span.events
        session.add(execution)
        TaskStateMachine.transition(task, "completed")
        session.add(task)
    await task_logger.updated(before, task, executing_agent_id=execution.agent_id, execution_path=execution_path)

    await span.emit("job.completed", {"path": "delegated"})


def _merge_skills(
    current_skills: dict[str, float] | None,
    final_state: GraphState,
) -> dict[str, float]:
    """Carry existing skills forward — reflect job applies the deltas after LLM reflection."""
    return dict(current_skills or {})


