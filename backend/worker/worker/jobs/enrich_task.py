from __future__ import annotations

import logging
import uuid
from typing import Any

from core.coordination.task_state import TaskStateMachine
from core.database import get_session
from core.eventing.activity.task_stream_logger import TaskStreamLogger
from core.intelligence.enrichment import EnrichmentOverrides, enrich
from core.repositories.task_repository import TaskRepository

from worker.context import get_worker_context
from worker.span import ArqJobMeta

logger = logging.getLogger(__name__)


async def enrich_task(
    ctx: dict[str, Any],
    task_id: str,
    workspace_id: str,
    overrides: dict[str, Any] | None,
) -> None:
    """Enrich a newly created Task with LLM-derived metadata and release it to bidding.

    Migrated from api/api/routers/tasks.py:enrich_and_release (FastAPI BackgroundTask).
    ARQ provides durability and automatic retry that BackgroundTask cannot — if the
    worker crashes mid-enrichment the job is retried; if enrich() raises, ARQ retries
    up to max_tries. A BackgroundTask is silently lost on any process exit.

    The creating request commits the task row (status="enriching") before enqueuing
    this job, so the task is guaranteed visible to this session.

    On retry: if a previous attempt already transitioned the task to "open" or a
    terminal state, both session blocks detect this via status checks and return
    early — no duplicate bidding events are published.
    """
    wctx = get_worker_context()
    meta = ArqJobMeta.from_ctx(ctx)
    overrides_obj = EnrichmentOverrides(**overrides) if overrides else None

    async with get_session() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(uuid.UUID(task_id))
        if task is None:
            logger.warning("enrich_task: task=%s not found — skipping", task_id)
            return

        if TaskStateMachine.is_terminal(task.status) or task.status == "open":
            logger.info(
                "enrich_task: task=%s already at %s on try=%d — skipping",
                task_id,
                task.status,
                meta.job_try,
            )
            return

        title = task.title
        description = task.description

    result = await enrich(title, description, wctx.llm_router, overrides_obj)

    async with get_session() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(uuid.UUID(task_id))
        if task is None:
            logger.warning("enrich_task: task=%s not found on write — skipping", task_id)
            return
        if TaskStateMachine.is_terminal(task.status) or task.status == "open":
            logger.info(
                "enrich_task: task=%s reached %s before write session on try=%d — skipping",
                task_id,
                task.status,
                meta.job_try,
            )
            return
        task.required_skills = result.required_skills
        task.difficulty = result.difficulty
        task.task_type = result.task_type
        task.domain_tags = result.domain_tags
        TaskStateMachine.transition(task, "open")
        await task_repo.save(task)

    stream_logger = TaskStreamLogger(wctx.bus.apublish)
    await stream_logger.task_created(task)

    logger.info("enrich_task: task=%s enriched and released to bidding", task_id)
