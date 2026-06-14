from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.tasks import Task


class InvalidTaskTransition(Exception):
    pass


class TaskStateMachine:
    # Maps current status → set of statuses it may legally move to.
    # reserved → open: allows a future cron job to release stale reservations
    # (Redis TTL expired; Postgres row still shows "reserved") back into bidding.
    TRANSITIONS: Mapping[str, frozenset[str]] = {
        "pending": frozenset({"enriching"}),
        "enriching": frozenset({"open"}),
        "open": frozenset({"reserved", "expired"}),
        "reserved": frozenset({"executing", "open"}),
        "executing": frozenset({"completed", "failed", "expired", "open"}),
    }

    @classmethod
    def transition(cls, task: Task, new_status: str) -> None:
        allowed = cls.TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise InvalidTaskTransition(
                f"Cannot transition task {task.id} from {task.status!r} to {new_status!r}. "
                f"Allowed: {sorted(allowed) or 'none (terminal state)'}"
            )
        task.status = new_status

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        return status not in cls.TRANSITIONS
