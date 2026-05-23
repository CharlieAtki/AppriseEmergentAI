from __future__ import annotations

import dataclasses
import uuid

from core.bus.common import Snapshot, StateActionEvent, StateChangeEvent


@dataclasses.dataclass(frozen=True, kw_only=True)
class TaskSnapshot(Snapshot):
    id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    parent_task_id: uuid.UUID | None
    title: str
    status: str
    task_type: str | None
    required_skills: dict | None
    difficulty: float | None
    domain_tags: dict | None


@dataclasses.dataclass(kw_only=True)
class TaskCreatedEvent(StateActionEvent[TaskSnapshot]):
    workspace_id: uuid.UUID


@dataclasses.dataclass(kw_only=True)
class TaskUpdatedEvent(StateChangeEvent[TaskSnapshot]):
    workspace_id: uuid.UUID


@dataclasses.dataclass(kw_only=True)
class TaskDeletedEvent(StateActionEvent[TaskSnapshot]):
    workspace_id: uuid.UUID
