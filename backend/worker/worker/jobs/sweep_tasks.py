from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from core.config import settings
from core.coordination.task_state import TaskStateMachine
from core.database import get_session
from core.eventing.activity.task_logger import TaskActivityLogger
from core.eventing.events.task_events import TaskSnapshot
from core.models.tasks import Task
from worker.context import get_worker_context

logger = logging.getLogger(__name__)


async def sweep_tasks(ctx: dict[str, Any]) -> None:
    """Cron job — runs every 5 minutes.

    Three sweeps:
    1. Stuck-open: ``"open"`` tasks idle longer than TASK_OPEN_TIMEOUT_SECONDS → ``"expired"``.
    2. Deadline violations: tasks with deadline_at in the past (open/executing) → ``"expired"``.
    3. Stale reservations: ``"reserved"`` tasks whose Redis TTL has long expired but whose
       Postgres row was never transitioned → ``"open"`` so they re-enter bidding.

    No LLM calls. No JobSpan. Events fired after the DB commit so handlers see final state.
    """
    wctx = get_worker_context()
    task_logger = TaskActivityLogger(wctx.event_bus.apublish)

    now = datetime.now(UTC)
    open_cutoff = now - timedelta(seconds=settings.TASK_OPEN_TIMEOUT_SECONDS)
    reserved_cutoff = now - timedelta(seconds=settings.TASK_RESERVED_TIMEOUT_SECONDS)

    transitioned: list[tuple[TaskSnapshot, Task]] = []

    async with get_session() as session:
        stuck_open = (
            (
                await session.execute(
                    select(Task).where(
                        Task.status == "open",
                        Task.updated_at < open_cutoff,
                        Task.deadline_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        deadline_expired = (
            (
                await session.execute(
                    select(Task).where(
                        Task.status.in_(["open", "executing"]),
                        Task.deadline_at.is_not(None),
                        Task.deadline_at < now,
                    )
                )
            )
            .scalars()
            .all()
        )

        stale_reserved = (
            (
                await session.execute(
                    select(Task).where(
                        Task.status == "reserved",
                        Task.updated_at < reserved_cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )

        for task in (*stuck_open, *deadline_expired):
            before = TaskSnapshot.from_domain(task)
            TaskStateMachine.transition(task, "expired")
            session.add(task)
            transitioned.append((before, task))

        for task in stale_reserved:
            before = TaskSnapshot.from_domain(task)
            TaskStateMachine.transition(task, "open")
            session.add(task)
            transitioned.append((before, task))

    for before, task in transitioned:
        await task_logger.updated(before, task)

    logger.debug(
        "sweep_tasks: expired=%d released=%d total=%d",
        len(stuck_open) + len(deadline_expired),
        len(stale_reserved),
        len(transitioned),
    )
