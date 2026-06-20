from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.coordination.task_state import TaskStateMachine
from core.database import get_session
from core.eventing.activity.base import PublishFn
from core.eventing.activity.task_logger import TaskActivityLogger
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskSnapshot, TaskUpdatedEvent
from core.models.tasks import TaskExecution
from core.repositories.task_repository import TaskRepository
from sqlalchemy import select

if TYPE_CHECKING:
    from arq import ArqRedis
    from core.models.tasks import Task
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class RollupSubtaskHandler(EventHandler[TaskUpdatedEvent]):
    """Promotes a parent task to terminal when all its subtasks reach a terminal state.

    Fires on every ``TaskUpdatedEvent`` where ``status`` changed. Ignores events
    for root tasks (``parent_task_id is None``) and non-terminal subtask statuses.

    When the last sibling goes terminal, ``_evaluate_parent`` checks that ALL siblings
    are terminal (concurrent-safe guard against double-rollup), transitions the parent
    to "completed" or "failed" (failed wins), emits a ``TaskUpdatedEvent`` for the
    parent, and enqueues a ``reflect`` job for the coordinator agent.

    ``publish`` is the in-process ``EventBus.apublish`` callable used to fire the
    parent's ``TaskUpdatedEvent`` — not the cross-process Redis Streams bus.
    """

    arq_queue: ArqRedis
    publish: PublishFn

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status"):
            return
        if not TaskStateMachine.is_terminal(event.state.status):
            return
        if event.state.parent_task_id is None:
            return
        try:
            parent_before: TaskSnapshot | None = None
            parent_after: Task | None = None
            reflect_agent_id: uuid.UUID | None = None
            reflect_execution_id: uuid.UUID | None = None

            async with get_session() as session:
                (
                    parent_before,
                    parent_after,
                    reflect_agent_id,
                    reflect_execution_id,
                ) = await self._evaluate_parent(session, event)

            if parent_before is not None and parent_after is not None:
                task_logger = TaskActivityLogger(self.publish)
                await task_logger.updated(parent_before, parent_after)

            if (
                reflect_agent_id is not None
                and reflect_execution_id is not None
                and parent_after is not None
            ):
                # Session is closed; scalar access is safe because SessionLocal uses
                # expire_on_commit=False — attributes remain readable after commit.
                parent_status = parent_after.status
                await self.arq_queue.enqueue_job(
                    "reflect",
                    agent_id=str(reflect_agent_id),
                    task_id=str(event.state.parent_task_id),
                    workspace_id=str(event.state.workspace_id),
                    execution_id=str(reflect_execution_id),
                    status=parent_status,
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
    ) -> tuple[TaskSnapshot | None, Task | None, uuid.UUID | None, uuid.UUID | None]:
        """Promote the parent task if all siblings have reached a terminal state.

        Returns (before_snapshot, parent_task, reflect_agent_id, execution_id) when rollup
        occurs, or (None, None, None, None) when it does not.

        execution_id is the parent's decompose execution (the coordinator's execution record).
        quality_score is no longer passed — the reflect job loads it directly from the DB.
        """
        parent_id = event.state.parent_task_id
        workspace_id = event.state.workspace_id

        task_repo = TaskRepository(session)
        siblings = await task_repo.get_siblings(parent_id, workspace_id)

        if not siblings:
            return None, None, None, None
        if not all(TaskStateMachine.is_terminal(s.status) for s in siblings):
            return None, None, None, None

        parent = await task_repo.get_by_id(parent_id)
        if parent is None or TaskStateMachine.is_terminal(parent.status):
            return None, None, None, None  # already resolved — concurrent rollup guard

        before = TaskSnapshot.from_domain(parent)
        any_failed = any(s.status == "failed" for s in siblings)
        TaskStateMachine.transition(parent, "failed" if any_failed else "completed")
        await task_repo.save(parent)

        execution_id: uuid.UUID | None = (
            await session.execute(
                select(TaskExecution.id)
                .where(
                    TaskExecution.task_id == parent_id,
                    TaskExecution.execution_path == "decompose",
                )
                .limit(1)
            )
        ).scalar()

        reflect_agent = parent.coordinator_agent_id or parent.created_by_agent_id
        return before, parent, reflect_agent, execution_id
