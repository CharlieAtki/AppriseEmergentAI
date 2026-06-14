from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import selectinload

from core.config import settings
from core.eventing.activity.task_logger import TaskActivityLogger
from core.eventing.activity.task_stream_logger import TaskStreamLogger
from core.agents.agent import build_initial_state
from core.agents.graphs.state import GraphState
from core.agents.scoring import score_outcome
from core.coordination.contract_net import issue_cfp
from core.coordination.decompose import decompose_and_publish
from core.coordination.task_context import MAX_DELEGATION_DEPTH, TaskContext
from core.coordination.task_state import TaskStateMachine
from core.eventing.events.task_events import TaskSnapshot
from core.intelligence.call_types import CallType
from core.intelligence.context import AgentContext, TaskEvaluationContext
from core.intelligence.prompts import decompose as decompose_prompt
from core.intelligence.prompts import evaluate
from core.intelligence.prompts.evaluate import EvaluateResponse
from core.models.agents import Agent
from core.models.tasks import Task, TaskExecution
from worker.context import get_worker_context
from worker.span import ArqJobMeta, JobSpan

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from worker.context import WorkerContext

logger = logging.getLogger(__name__)


async def execute_task(
    ctx: dict[str, Any],
    agent_id: str,
    task_id: str,
    workspace_id: str,
) -> None:
    """
    Orchestrates the end-to-end execution of a task by an agent, including evaluation, delegation, self-execution, result persistence, and downstream event publishing.
    
    Performs the following high-level steps:
    - Loads Agent and Task state, enforcing a terminal-state idempotency guard.
    - Creates or reuses a TaskExecution row and marks the task as executing.
    - Asks the LLM to evaluate whether to decompose, issue a call-for-proposals (CFP), or self-execute.
    - Acts on the decision: create subtasks for decomposition, release the task back to the pool for CFP, or run a LangGraph-based self-execution.
    - If self-executing, runs the graph, scores the outcome, and atomically writes execution, agent, snapshot, and task updates.
    - Publishes downstream events (stream events and job lifecycle events).

    On any exception after the execution row is committed, writes failure state for the execution and transitions the task to "failed" (when appropriate) to avoid leaving dangling rows, logs failures, and re-raises the exception for the job system to record.
    """
    wctx = get_worker_context()
    meta = ArqJobMeta.from_ctx(ctx)
    async with JobSpan(
        uuid.UUID(agent_id), uuid.UUID(task_id), uuid.UUID(workspace_id),
        redis_publish=wctx.redis.publish,
        meta=meta,
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

        # task_logger   — in-process EventBus; fires typed DomainEvents to same-process
        #                 handlers (RollupSubtaskHandler, etc.). Does not cross process boundary.
        # stream_logger — Redis Streams; fires typed StreamEvents consumed by
        #                 TaskStreamSubscriber in any worker process. Durable, at-least-once.
        task_logger = TaskActivityLogger(wctx.event_bus.apublish)
        stream_logger = TaskStreamLogger(wctx.bus.apublish)
        execution: TaskExecution | None = None
        # Tracks the task status as last committed to DB. In-memory task.status
        # can diverge from the DB if a session raises after the ORM mutation but
        # before commit. The failure path uses this to avoid skipping cleanup when
        # the DB row is still at "executing" but task.status in-memory shows a later value.
        committed_task_status = task.status

        try:
            # ── Phase 2: WRITE EXECUTION ROW ───────────────────────────────────
            # Idempotency guard: if ARQ retries a crashed job, the execution row
            # already exists and task.status is already "executing". Reuse it to
            # avoid an InvalidTaskTransition on the state machine transition.
            existing = next(
                (e for e in agent.task_executions if e.task_id == task.id and e.status == "executing"),
                None,
            )
            if existing is not None:
                execution = existing
                committed_task_status = task.status  # already "executing"
            else:
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
            agent_ctx = AgentContext(
                name=agent.name,
                skills=agent.skills or {},
                influence=agent.influence or 0.0,
            )
            task_ctx = TaskEvaluationContext(
                title=task.title,
                description=task.description,
                required_skills=task.required_skills or {},
                difficulty=task.difficulty,
                domain_tags=task.domain_tags or {},
                task_type=task.task_type,
                delegation_depth=provenance.delegation_depth,
                depth_exceeded=depth_exceeded,
            )

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
                    subtasks = await decompose_and_publish(
                        agent, task, specs, session,
                        task_ctx=provenance,
                        task_logger=task_logger,
                    )
                # Session committed — subtasks are now visible to all connections.
                for subtask in subtasks:
                    await stream_logger.task_created(subtask)

                await _finalise_execution(span, execution, task, "completed", task_logger, execution_path="decompose")
                return

            if decision.decision == "cfp":
                await span.emit("agent.issuing_cfp", {"reasoning": decision.reasoning})
                await issue_cfp(task, agent, stream_logger)
                await _release_to_pool(span, execution, task, wctx.redis, task_logger, stream_logger)
                return

            # ── Phase 5: SELF-EXECUTE via LangGraph ──────────────────────────────
            # No open DB session during graph execution — connections are a scarce resource.
            await span.emit("agent.executing", {})
            initial_state = build_initial_state(agent, task)
            graph_key = task.task_type if task.task_type in wctx.graphs else "general"
            final_state: GraphState = await wctx.graphs[graph_key].ainvoke(
                initial_state
            )

            quality = score_outcome(task, final_state)
            await span.emit("agent.scored", {"quality_score": quality})

            # ── Phase 6: WRITE RESULTS (single atomic commit) ────────────────────
            before_completed = TaskSnapshot.from_domain(task, executing_agent_id=agent.id)
            async with span.session() as session:
                execution.status         = "completed"
                execution.execution_path = "self_execute"
                execution.quality_score  = quality
                execution.artifact        = final_state.get("artifact")
                execution.tool_trace     = final_state["tool_trace"]   # structured {tool,args,result} records
                execution.completed_at   = datetime.now(timezone.utc)
                session.add(execution)

                # Flat entropy decay across all skills — one step per task completion.
                # Reflect applies targeted, quality-weighted deltas to used skills on top.
                # Influence is updated downstream by AgentCreditHandler.
                if agent.skills:
                    agent.skills = {
                        k: max(0.0, v * (1.0 - settings.SKILL_DECAY_RATE))
                        for k, v in agent.skills.items()
                    }
                agent.updated_at = datetime.now(timezone.utc)
                session.add(agent)

                TaskStateMachine.transition(task, "completed")
                session.add(task)

            await task_logger.updated(
                before_completed, task,
                executing_agent_id=agent.id,
                quality_score=quality,
                execution_id=execution.id,
                execution_path="self_execute",
            )

            await stream_logger.task_completed(task, agent_id, quality)

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
                    await task_logger.updated(
                        before_failed, task,
                        executing_agent_id=agent.id if execution is not None else None,
                        execution_id=execution.id if execution is not None else None,
                        execution_path=execution.execution_path if execution is not None else None,
                    )
            except Exception:
                logger.exception(
                    "execute_task: could not write failure state for task=%s", task_id
                )
            raise



async def _release_to_pool(
    span: JobSpan,
    execution: TaskExecution,
    task: Task,
    redis: Redis,
    task_logger: TaskActivityLogger,
    stream_logger: TaskStreamLogger,
) -> None:
    """CFP path: mark execution done and release the task back to the bidding pool.

    The deciding agent's execution record is closed (execution → "completed") and the
    task returns to "open" — it was never worked on, only routed. The Redis reservation
    key is deleted immediately so the next winner is not blocked by the TTL.

    stream_logger.task_created() re-publishes the task to stream:task so standard
    bidding can pick it up. This is separate from the cfp_issued event fired by the
    caller (issue_cfp) — that event targets the CFP stream which has no subscriber yet.
    Both must fire: cfp_issued records that a negotiation round was initiated;
    task_created triggers actual re-bidding now.
    """
    before = TaskSnapshot.from_domain(task, executing_agent_id=execution.agent_id)
    async with span.session() as session:
        execution.status          = "completed"
        execution.execution_path  = "cfp"
        execution.completed_at    = datetime.now(timezone.utc)
        execution.tool_trace      = span.events
        session.add(execution)
        # Only set coordinator if not already tracked — preserves grandparent coordinator
        # on tasks that were previously decomposed before being CFP'd.
        if task.coordinator_agent_id is None:
            task.coordinator_agent_id = execution.agent_id
        # Increment depth so the existing depth guard prevents infinite CFP loops.
        task.delegation_depth = (task.delegation_depth or 0) + 1
        TaskStateMachine.transition(task, "open")
        session.add(task)
    await task_logger.updated(before, task, executing_agent_id=execution.agent_id, execution_path="cfp")

    await redis.delete(f"reservation:{task.workspace_id}:{task.id}")

    await stream_logger.task_created(task)

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
        execution.status          = status
        execution.execution_path  = execution_path
        execution.completed_at    = datetime.now(timezone.utc)
        execution.tool_trace      = span.events
        session.add(execution)
        TaskStateMachine.transition(task, "completed")
        session.add(task)
    await task_logger.updated(before, task, executing_agent_id=execution.agent_id, execution_path=execution_path)

    await span.emit("job.completed", {"path": "delegated"})




