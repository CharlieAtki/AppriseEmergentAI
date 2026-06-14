from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from core.intelligence.reflection.types import ReflectContext
from core.models.agents import Agent
from core.models.tasks import Task, TaskExecution
from worker.context import get_worker_context
from worker.span import ArqJobMeta, JobSpan

logger = logging.getLogger(__name__)


async def reflect(
    ctx: Mapping[str, Any],
    agent_id: str,
    task_id: str,
    workspace_id: str,
    execution_id: str,
    status: str,
) -> None:
    """ARQ job: post-execution reflection pipeline.

    Thin lifecycle wrapper with three responsibilities only — load, run, stamp:

    1. Load: fetch Task, Agent, and TaskExecution from Postgres in a single session
       that closes before any stage runs. All state is captured in a frozen
       ``ReflectContext`` so stages never hold a live ORM reference.

    2. Idempotency guard: if ``execution.reflect_completed_at`` is already set, the
       pipeline has already run for this execution — return immediately. This makes
       ARQ retries safe regardless of which stage failed or how far the pipeline got.

    3. Run: delegate to ``WorkerContext.reflection_manager`` which sequences the
       four stages (reflect → skills → rules → episodic). Per-stage failures are
       isolated — a failing stage is logged and skipped, not a job failure.

    4. Stamp: write ``reflect_completed_at`` after all stages complete. If the process
       dies between run() and stamp, ARQ will retry and re-run all stages.

    Enqueued by ``ReflectJobHandler`` (self-execute path) and ``RollupSubtaskHandler``
    (decompose path) after a task reaches "completed" or "failed".
    """
    wctx = get_worker_context()
    meta = ArqJobMeta.from_ctx(ctx)
    async with JobSpan(
        uuid.UUID(agent_id),
        uuid.UUID(task_id),
        uuid.UUID(workspace_id),
        redis_publish=wctx.redis.publish,
        meta=meta,
    ) as span:
        # Load all state in one session. Session closes before any stage runs.
        async with span.session() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            agent = await session.get(Agent, uuid.UUID(agent_id))
            execution = await session.get(TaskExecution, uuid.UUID(execution_id))

        if not task or not agent or not execution:
            logger.warning(
                "reflect: missing records — task=%s agent=%s execution=%s — skipping",
                task_id,
                agent_id,
                execution_id,
            )
            return

        if status not in ("completed", "failed"):
            logger.warning(
                "reflect: invalid status=%r for execution=%s — skipping", status, execution_id
            )
            return

        # Idempotency guard — safe on ARQ retry.
        if execution.reflect_completed_at is not None:
            logger.info("reflect: already completed for execution=%s — skipping", execution_id)
            return

        step_count = len(execution.tool_trace) if execution.tool_trace else 0
        full_reflect = (task.difficulty or 1.0) >= 3.0 or step_count > 3

        rctx = ReflectContext(
            task_id=task.id,
            agent_id=agent.id,
            execution_id=execution.id,
            workspace_id=task.workspace_id,
            organisation_id=agent.organisation_id,
            task_title=task.title,
            task_description=task.description,
            task_type=task.task_type,
            required_skills=task.required_skills or {},
            difficulty=task.difficulty,
            domain_tags=task.domain_tags,
            status=status,
            artifact=execution.artifact,
            error=execution.error,
            tool_trace=tuple(execution.tool_trace or []),
            heuristic_score=execution.quality_score or 0.0,
            full_reflect=full_reflect,
            step_count=step_count,
            agent_skills=agent.skills or {},
        )

        result = await wctx.reflection_manager.run(rctx)

        await span.emit(
            "job.completed",
            {
                "quality_score": rctx.heuristic_score,
                "stages_run": result.stages_run,
                "stages_failed": result.stages_failed,
            },
        )
        logger.info(
            "reflect: agent=%s task=%s stages_run=%s stages_failed=%s quality_score=%.3f",
            agent_id,
            task_id,
            result.stages_run,
            result.stages_failed,
            rctx.heuristic_score,
        )

        if result.stages_failed:
            # Raise so ARQ retries. Per-stage idempotency guards (SkillSnapshot check
            # in _stage_skills, ProceduralKnowledgeLog/vector_store_ref in _stage_rules)
            # prevent double-writes — only the failed stages will re-run.
            raise RuntimeError(
                f"reflect pipeline partial failure — stages_failed={result.stages_failed}"
            )

        # Stamp only after all stages pass. Prevents the idempotency guard at the top
        # from short-circuiting ARQ retries when a previous attempt had partial failures.
        async with span.session() as session:
            exc = await session.get(TaskExecution, execution.id)
            if exc is not None:
                exc.reflect_completed_at = datetime.now(tz=UTC)
                session.add(exc)
