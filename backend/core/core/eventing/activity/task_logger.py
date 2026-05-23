"""Activity-logger facade for task domain events.

:class:`TaskActivityLogger` constructs the appropriate event payload from a
SQLAlchemy model and forwards it through ``publish``. It knows nothing about
handlers, the bus, or dispatch — its only job is translating a domain action
into a correctly shaped event.

Logger methods read scalar attributes from their argument. This works even on
detached SQLAlchemy instances, since SQLAlchemy keeps cached scalar values in
``__dict__`` after detach.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from core.eventing.activity.base import PublishFn
from core.eventing.events.task_events import TaskCreatedEvent, TaskDeletedEvent, TaskSnapshot, TaskUpdatedEvent

if TYPE_CHECKING:
    from core.models.tasks import Task


class TaskActivityLogger:
    """Endpoint-side facade that constructs task lifecycle events and publishes them after commit."""

    def __init__(self, publish: PublishFn) -> None:
        self._publish = publish

    async def created(self, task: Task) -> None:
        snapshot = TaskSnapshot.from_domain(task)
        await self._publish(TaskCreatedEvent(state=snapshot, workspace_id=task.workspace_id))

    async def updated(self, before: TaskSnapshot, after: Task) -> None:
        await self._publish(
            TaskUpdatedEvent(
                state=TaskSnapshot.from_domain(after),
                before=before,
                workspace_id=after.workspace_id,
            )
        )

    async def deleted(self, task: Task) -> None:
        snapshot = TaskSnapshot.from_domain(task)
        await self._publish(TaskDeletedEvent(state=snapshot, workspace_id=task.workspace_id))