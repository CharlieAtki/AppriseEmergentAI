from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.tasks import Task

MAX_DELEGATION_DEPTH = 5


@dataclass(frozen=True)
class TaskContext:
    task_id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    parent_task_id: uuid.UUID | None
    coordinator_agent_id: uuid.UUID | None
    created_by_agent_id: uuid.UUID | None
    delegation_depth: int

    @classmethod
    def from_task(cls, task: Task) -> TaskContext:
        return cls(
            task_id=task.id,
            workspace_id=task.workspace_id,
            organisation_id=task.organisation_id,
            parent_task_id=task.parent_task_id,
            coordinator_agent_id=task.coordinator_agent_id,
            created_by_agent_id=task.created_by_agent_id,
            delegation_depth=task.delegation_depth,
        )
