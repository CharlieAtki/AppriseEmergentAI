from __future__ import annotations

from typing import TYPE_CHECKING

from core.activity.base import ActivityLogger
from core.events.task_events import TaskCreatedEvent, TaskDeletedEvent, TaskSnapshot, TaskUpdatedEvent

if TYPE_CHECKING:
    from core.models.tasks import Task


class TaskActivityLogger(ActivityLogger):
    async def task_created(self, task: Task) -> None:
        snapshot = TaskSnapshot.from_domain(task)
        await self._publish(TaskCreatedEvent(state=snapshot, workspace_id=task.workspace_id))

    async def task_updated(self, before: Task, after: Task) -> None:
        await self._publish(
            TaskUpdatedEvent(
                state=TaskSnapshot.from_domain(after),
                before=TaskSnapshot.from_domain(before),
                workspace_id=after.workspace_id,
            )
        )

    async def task_deleted(self, task: Task) -> None:
        snapshot = TaskSnapshot.from_domain(task)
        await self._publish(TaskDeletedEvent(state=snapshot, workspace_id=task.workspace_id))
