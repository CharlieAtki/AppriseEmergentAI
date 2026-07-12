from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.agents.agent import build_initial_state
from core.agents.graphs.state import GraphState
from core.agents.scoring import score_outcome
from core.agents.tooling.registry import tool_registry
from core.config import settings
from core.coordination.config import CoordinationConfig, resolve_coordination_config
from core.coordination.decompose import decompose_subtasks
from core.coordination.task_context import TaskContext
from core.coordination.task_state import TaskStateMachine
from core.eventing.activity.task_logger import TaskActivityLogger
from core.eventing.activity.task_stream_logger import TaskStreamLogger
from core.eventing.events.task_events import TaskSnapshot
from core.intelligence import structured_call
from core.intelligence.call_types import CallType
from core.intelligence.context import AgentContext, TaskEvaluationContext
from core.intelligence.prompts import decompose as decompose_prompt
from core.intelligence.prompts import evaluate
from core.intelligence.prompts.evaluate import EvaluateResponse
from core.intelligence.signals import classify_influence
from core.repositories.agent_repository import AgentRepository
from core.repositories.org_repository import OrganisationRepository
from core.repositories.task_execution_repository import TaskExecutionRepository
from core.repositories.task_repository import TaskRepository
from core.repositories.tool_repository import ToolRepository
from core.repositories.workspace_repository import WorkspaceRepository
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from worker.context import get_worker_context
from worker.span import ArqJobMeta, JobSpan

if TYPE_CHECKING:
    from core.models.tasks import Task, TaskExecution
    from redis.asyncio import Redis

    from worker.context import WorkerContext


logger = logging.getLogger(__name__)

# Belt-and-braces fallback only — the API's PATCH route invalidates this key on
# every write (see api/routers/coordination_config.py). The TTL guards against
# any future write path that forgets to invalidate, not normal operation.
_COORDINATION_CONFIG_CACHE_TTL_SECONDS = 300


async def _resolve_coordination_config(
    wctx: WorkerContext, span: JobSpan, task: Task
) -> CoordinationConfig:
    """Cache-then-DB resolution of this task's effective coordination guards.

    Never imports api/ — reads Organisation/Workspace directly via core/ repositories,
    since the worker must not depend on the HTTP layer.
    """
    cache_key = f"coordination_config:{task.workspace_id}"
    cached = await wctx.redis.get(cache_key)
    if cached is not None:
        return CoordinationConfig(**json.loads(cached))

    async with span.session() as session:
        organisation = await OrganisationRepository(session).get_by_id(task.organisation_id)
        workspace = await WorkspaceRepository(session).get_by_id(task.workspace_id)

    org_override = (organisation.config or {}).get("coordination") if organisation else None
    workspace_override = (workspace.config or {}).get("coordination") if workspace else None
    coord_cfg = resolve_coordination_config(settings.coordination, org_override, workspace_override)

    await wctx.redis.set(
        cache_key, json.dumps(asdict(coord_cfg)), ex=_COORDINATION_CONFIG_CACHE_TTL_SECONDS
    )
    return coord_cfg


def _force_self_execute(
    task_id: uuid.UUID, reason: str, log_template: str, *log_args: object
) -> EvaluateResponse:
    """Shared shape for every coordination guard below: log why the LLM's
    decision is being overridden, then return the forced self_execute. Both
    the depth guard and the difficulty guard are "log + override" — only the
    triggering condition differs, so that's the only thing that should vary
    at each call site."""
    logger.warning(log_template, task_id, *log_args)
    return EvaluateResponse(decision="self_execute", reasoning=reason)


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
        uuid.UUID(agent_id),
        uuid.UUID(task_id),
        uuid.UUID(workspace_id),
        publish=wctx.centrifugo_publish,
        meta=meta,
    ) as span:
        # ── Phase 1: READ ──────────────────────────────────────────────────────
        async with span.session() as session:
            task_repo = TaskRepository(session)
            agent_repo = AgentRepository(session)
            task = await task_repo.get_for_execution(uuid.UUID(task_id))
            agent = await agent_repo.get_for_execution(uuid.UUID(agent_id))
            if agent is None or task is None:
                logger.warning(
                    "execute_task: agent=%s or task=%s not found — skipping",
                    agent_id,
                    task_id,
                )
                return

        # Guard: if this is a retry and the previous attempt already wrote a terminal
        # status, do not re-execute. The state machine would reject the transition anyway.
        if TaskStateMachine.is_terminal(task.status):
            logger.info(
                "execute_task: task=%s already terminal (%s) — skipping retry",
                task_id,
                task.status,
            )
            return

        # Build provenance context while task attributes are in-memory.
        # expire_on_commit=False on SessionLocal keeps scalar attrs after session close.
        provenance = TaskContext.from_task(task)
        coord_cfg = await _resolve_coordination_config(wctx, span, task)
        depth_exceeded = provenance.delegation_depth >= coord_cfg.max_delegation_depth

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
            # In-memory check using the already-loaded agent.task_executions — avoids a DB
            # round-trip on ARQ retry. The guard is caller-owned because the data is caller-owned.
            existing = next(
                (
                    e
                    for e in agent.task_executions
                    if e.task_id == task.id and e.status == "executing"
                ),
                None,
            )
            if existing is not None:
                execution = existing
                committed_task_status = task.status  # already "executing"
            else:
                before_executing = TaskSnapshot.from_domain(task, executing_agent_id=agent.id)
                async with span.session() as session:
                    task_repo = TaskRepository(session)
                    execution_repo = TaskExecutionRepository(session)
                    execution = await execution_repo.create(
                        workspace_id=task.workspace_id,
                        organisation_id=agent.organisation_id,
                        task_id=task.id,
                        agent_id=agent.id,
                    )
                    TaskStateMachine.transition(task, "executing")
                    await task_repo.save(task)
                committed_task_status = task.status  # "executing"
                await task_logger.updated(before_executing, task, executing_agent_id=agent.id)

            await span.emit("job.started", {"task_type": task.task_type})

            # ── Phase 3: LLM EVALUATE ────────────────────────────────────────────
            await span.emit("agent.evaluating", {})
            agent_influence = agent.influence or 0.0
            agent_ctx = AgentContext(
                name=agent.name,
                skills=agent.skills or {},
                influence=agent_influence,
                influence_tier=classify_influence(agent_influence),
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

            decision = await structured_call.run(
                wctx.llm_router,
                CallType.EVALUATE,
                evaluate.build_prompt(
                    agent_ctx, task_ctx, coord_cfg.decompose_difficulty_threshold
                ),
                evaluate.parse,
                fallback=EvaluateResponse(decision="self_execute", reasoning="parse fallback"),
            )

            # Depth guard: blocks ANY non-self_execute decision (decompose or cfp) once
            # the delegation chain is too deep — it's a ceiling on the whole ContractNet
            # chain, not specific to one strategy.
            if depth_exceeded and decision.decision != "self_execute":
                decision = _force_self_execute(
                    task.id,
                    "depth guard",
                    "execute_task: depth guard forcing self_execute for task=%s (depth=%d)",
                    provenance.delegation_depth,
                )

            # Difficulty guard: unlike the depth guard, this targets decompose only — a
            # cfp handoff to a better-skilled agent isn't decomposition, so a low
            # difficulty score doesn't block it. This is the APP-8 fix: the LLM's soft
            # "prefer decompose when difficulty >= threshold" guideline is no longer the
            # only thing enforcing this.
            decompose_below_threshold = (
                decision.decision == "decompose"
                and (task.difficulty or 0) < coord_cfg.decompose_difficulty_threshold
            )
            if decompose_below_threshold:
                decision = _force_self_execute(
                    task.id,
                    "difficulty guard",
                    "execute_task: difficulty guard forcing self_execute for task=%s "
                    "(difficulty=%s < threshold=%s)",
                    task.difficulty,
                    coord_cfg.decompose_difficulty_threshold,
                )

            # ── Phase 4: ACT ON DECISION ─────────────────────────────────────────
            if decision.decision == "decompose":
                await span.emit("agent.decomposing", {"reasoning": decision.reasoning})
                try:
                    decompose_resp = await structured_call.call_and_parse(
                        wctx.llm_router,
                        CallType.DECOMPOSE,
                        decompose_prompt.build_prompt(agent_ctx, task_ctx),
                        decompose_prompt.parse,
                    )
                except ValidationError as exc:
                    logger.warning(
                        "execute_task: decompose parse failed for task=%s, forcing self_execute: %s",
                        task.id,
                        exc,
                    )
                    decision = EvaluateResponse(
                        decision="self_execute", reasoning="decompose parse fallback"
                    )
                else:
                    specs = [s.model_dump() for s in decompose_resp.subtasks]

                    async with span.session() as session:
                        task_repo = TaskRepository(session)
                        subtasks = await decompose_subtasks(
                            agent,
                            task,
                            specs,
                            task_repo,
                            task_ctx=provenance,
                        )
                    # Session committed — subtasks are now visible to all connections.
                    # Both publishes happen here, not inside decompose_subtasks, so
                    # neither can fire for a subtask that failed to commit.
                    for subtask in subtasks:
                        await task_logger.created(subtask)
                        await stream_logger.task_created(subtask)

                    await _finalise_execution(
                        span, execution, task, "completed", task_logger, execution_path="decompose"
                    )
                    return

            if decision.decision == "cfp":
                await span.emit("agent.issuing_cfp", {"reasoning": decision.reasoning})
                await stream_logger.cfp_issued(task, agent)
                await _release_to_pool(
                    span, execution, task, wctx.redis, task_logger, stream_logger
                )
                return

            # ── Phase 5: SELF-EXECUTE via LangGraph ──────────────────────────────
            # Resolve workspace-scoped tools before graph invocation. Session closes
            # before ainvoke — no open DB connection during graph execution.
            await span.stream.task_executing(task.workspace_id, task.id, agent.id)
            async with span.session() as session:
                tools, entries = await tool_registry.build_for_task_type(
                    task_type=task.task_type or "general",
                    workspace_id=task.workspace_id,
                    memory=wctx.memory,
                    agent_id=agent.id,
                    organisation_id=agent.organisation_id,
                    repo=ToolRepository(session),
                    artifact_store=wctx.artifact_store,
                )
            model_with_tools = wctx.llm_router.get_chat_model(CallType.EXECUTE).bind_tools(tools)
            run_config = RunnableConfig(
                configurable={
                    "model": model_with_tools,
                    "tool_map": {t.name: t for t in tools},
                    "skill_tag_map": tool_registry.get_skill_tag_map(entries),
                }
            )
            initial_state = build_initial_state(agent, task)
            final_state: GraphState = await wctx.graphs["universal"].ainvoke(
                initial_state, config=run_config
            )

            quality = score_outcome(final_state)
            await span.emit("agent.scored", {"quality_score": quality})

            # ── Phase 6: WRITE RESULTS (single atomic commit) ────────────────────
            before_completed = TaskSnapshot.from_domain(task, executing_agent_id=agent.id)
            async with span.session() as session:
                task_repo = TaskRepository(session)
                agent_repo = AgentRepository(session)
                execution_repo = TaskExecutionRepository(session)
                execution.status = "completed"
                execution.execution_path = "self_execute"
                execution.quality_score = quality
                execution.artifact = final_state["artifact"]
                execution.artifact_id = final_state["artifact_id"]
                execution.skill_tags_used = final_state["skill_tags_used"] or []
                execution.tool_trace = final_state["tool_trace"]
                execution.completed_at = datetime.now(UTC)
                await execution_repo.save(execution)

                # Flat entropy decay across all skills — one step per task completion.
                # Reflect applies targeted, quality-weighted deltas to used skills on top.
                # Influence is updated downstream by AgentCreditHandler.
                if agent.skills:
                    agent.skills = {
                        k: max(0.0, v * (1.0 - settings.SKILL_DECAY_RATE))
                        for k, v in agent.skills.items()
                    }
                agent.updated_at = datetime.now(UTC)
                await agent_repo.save(agent)

                TaskStateMachine.transition(task, "completed")
                await task_repo.save(task)

            await task_logger.updated(
                before_completed,
                task,
                executing_agent_id=agent.id,
                quality_score=quality,
                execution_id=execution.id,
                execution_path="self_execute",
            )

            await stream_logger.task_completed(task, agent_id, quality)

            await span.stream.task_completed(task.workspace_id, task.id, agent.id, quality)

            logger.info(
                "execute_task: agent=%s task=%s quality=%.3f",
                agent_id,
                task_id,
                quality,
            )

        except BaseException as exc:
            # Write failure state so the task and execution rows are not left dangling.
            # The session that failed has already rolled back; open a fresh one.
            # execution may be None if Phase 2 never committed (its session rolled back,
            # leaving the task at "reserved" — safe to skip the execution update in that case).
            logger.exception("execute_task failed: agent=%s task=%s", agent_id, task_id)
            before_failed: TaskSnapshot | None = None
            try:
                async with span.session() as session:
                    task_repo = TaskRepository(session)
                    execution_repo = TaskExecutionRepository(session)
                    if execution is not None:
                        execution.status = "failed"
                        execution.completed_at = datetime.now(UTC)
                        execution.error = {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                        await execution_repo.save(execution)
                        await span.stream.task_failed(
                            task.workspace_id, task.id, agent.id, error_message=str(exc)
                        )
                    if not TaskStateMachine.is_terminal(committed_task_status):
                        task.status = (
                            committed_task_status  # reset in-memory to last committed value
                        )
                        before_failed = TaskSnapshot.from_domain(task)
                        TaskStateMachine.transition(task, "failed")
                        await task_repo.save(task)
                if before_failed is not None:
                    await task_logger.updated(
                        before_failed,
                        task,
                        executing_agent_id=agent.id if execution is not None else None,
                        execution_id=execution.id if execution is not None else None,
                        execution_path=execution.execution_path if execution is not None else None,
                    )
            except Exception:
                logger.exception("execute_task: could not write failure state for task=%s", task_id)
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
    caller — that event targets the CFP stream which has no subscriber yet.
    Both must fire: cfp_issued records that a negotiation round was initiated;
    task_created triggers actual re-bidding now.
    """
    before = TaskSnapshot.from_domain(task, executing_agent_id=execution.agent_id)
    async with span.session() as session:
        task_repo = TaskRepository(session)
        execution_repo = TaskExecutionRepository(session)
        execution.status = "completed"
        execution.execution_path = "cfp"
        execution.completed_at = datetime.now(UTC)
        execution.tool_trace = span.events
        await execution_repo.save(execution)
        # Only set coordinator if not already tracked — preserves grandparent coordinator
        # on tasks that were previously decomposed before being CFP'd.
        if task.coordinator_agent_id is None:
            task.coordinator_agent_id = execution.agent_id
        # Increment depth so the existing depth guard prevents infinite CFP loops.
        task.delegation_depth = (task.delegation_depth or 0) + 1
        TaskStateMachine.transition(task, "open")
        await task_repo.save(task)
    await task_logger.updated(
        before, task, executing_agent_id=execution.agent_id, execution_path="cfp"
    )

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
        task_repo = TaskRepository(session)
        execution_repo = TaskExecutionRepository(session)
        execution.status = status
        execution.execution_path = execution_path
        execution.completed_at = datetime.now(UTC)
        execution.tool_trace = span.events
        await execution_repo.save(execution)
        TaskStateMachine.transition(task, "completed")
        await task_repo.save(task)
    await task_logger.updated(
        before, task, executing_agent_id=execution.agent_id, execution_path=execution_path
    )

    await span.emit("job.completed", {"path": "delegated"})
