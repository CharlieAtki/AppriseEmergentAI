from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from core.coordination.task_state import TaskStateMachine
from core.database import get_session
from core.eventing.activity.base import PublishFn
from core.eventing.activity.task_logger import TaskActivityLogger
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskSnapshot, TaskUpdatedEvent
from core.models.tasks import Task

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arq import ArqRedis

logger = logging.getLogger(__name__)

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "expired"})


@dataclass
class RollupSubtaskHandler(EventHandler[TaskUpdatedEvent]):
    arq_queue: ArqRedis
    publish: PublishFn

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status"):
            return
        if event.state.status not in TERMINAL_STATUSES:
            return
        if event.state.parent_task_id is None:
            return
        try:
            parent_before: TaskSnapshot | None = None
            parent_after: Task | None = None
            reflect_agent_id: uuid.UUID | None = None

            async with get_session() as session:
                parent_before, parent_after, reflect_agent_id = await self._evaluate_parent(session, event)

            # Publish AFTER the session commits so downstream handlers see the
            # parent's new status in the DB, not the pre-commit state.
            if parent_before is not None and parent_after is not None:
                task_logger = TaskActivityLogger(self.publish)
                await task_logger.updated(parent_before, parent_after)

            if reflect_agent_id is not None:
                await self.arq_queue.enqueue_job(
                    "reflect",
                    agent_id=str(reflect_agent_id),
                    task_id=str(event.state.parent_task_id),
                    workspace_id=str(event.state.workspace_id),
                )
        except Exception:
            logger.exception(
                "RollupSubtaskHandler failed for task=%s parent=%s",
                event.state.id,
                event.state.parent_task_id,
            )

    async def _evaluate_parent(
        self,
        session: AsyncSession,
        event: TaskUpdatedEvent,
    ) -> tuple[TaskSnapshot | None, Task | None, uuid.UUID | None]:
        """Promote the parent task if all siblings have reached a terminal state.

        Returns (before_snapshot, parent_task, reflect_agent_id) when rollup
        occurs, or (None, None, None) when it does not. The caller publishes the
        parent event and enqueues the reflect job after the session commits.
        """
        parent_id = event.state.parent_task_id
        workspace_id = event.state.workspace_id

        siblings = (await session.execute(
            select(Task).where(
                Task.parent_task_id == parent_id,
                Task.workspace_id == workspace_id,
            )
        )).scalars().all()

        if not siblings:
            return None, None, None
        if not {s.status for s in siblings}.issubset(TERMINAL_STATUSES):
            return None, None, None

        parent = await session.get(Task, parent_id)
        if parent is None or parent.status in TERMINAL_STATUSES:
            return None, None, None  # already resolved — concurrent rollup guard

        before = TaskSnapshot.from_domain(parent)
        any_failed = any(s.status == "failed" for s in siblings)
        TaskStateMachine.transition(parent, "failed" if any_failed else "completed")

        return before, parent, parent.coordinator_agent_id or parent.created_by_agent_id
