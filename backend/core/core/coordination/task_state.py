from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.tasks import Task


class InvalidTaskTransition(Exception):
    pass

# Todo: Is this clean - is this texonomy? do we want to have a graph style that can be traced?
class TaskStateMachine:
    # Maps current status → set of statuses it may legally move to.
    # reserved → open: allows a future cron job to release stale reservations
    # (Redis TTL expired; Postgres row still shows "reserved") back into bidding.
    TRANSITIONS: dict[str, set[str]] = {
        "pending": {"enriching"},
        "enriching": {"open"},
        "open": {"reserved", "expired"},
        "reserved": {"executing", "open"},
        "executing": {"completed", "failed", "expired", "open"},
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
