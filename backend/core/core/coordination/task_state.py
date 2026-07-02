from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from core.models.enums import TaskStatus

if TYPE_CHECKING:
    from core.models.tasks import Task


class InvalidTaskTransition(Exception):
    pass


class TaskStateMachine:
    # Maps current status → set of statuses it may legally move to.
    # reserved → open: allows a future cron job to release stale reservations
    # (Redis TTL expired; Postgres row still shows "reserved") back into bidding.
    TRANSITIONS: Mapping[TaskStatus, frozenset[TaskStatus]] = {
        TaskStatus.pending: frozenset({TaskStatus.enriching}),
        TaskStatus.enriching: frozenset({TaskStatus.open}),
        TaskStatus.open: frozenset({TaskStatus.reserved, TaskStatus.expired}),
        TaskStatus.reserved: frozenset({TaskStatus.executing, TaskStatus.open}),
        TaskStatus.executing: frozenset(
            {TaskStatus.completed, TaskStatus.failed, TaskStatus.expired, TaskStatus.open}
        ),
    }

    @classmethod
    def transition(cls, task: Task, new_status: TaskStatus) -> None:
        allowed = cls.TRANSITIONS.get(task.status, frozenset())
        if new_status not in allowed:
            raise InvalidTaskTransition(
                f"Cannot transition task {task.id} from {task.status!r} to {new_status!r}. "
                f"Allowed: {sorted(allowed) or 'none (terminal state)'}"
            )
        task.status = new_status

    @classmethod
    def is_terminal(cls, status: TaskStatus) -> bool:
        return status not in cls.TRANSITIONS
