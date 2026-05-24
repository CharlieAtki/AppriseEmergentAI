from __future__ import annotations

import dataclasses
import uuid
from typing import Literal

from core.eventing.bus import Snapshot, StateActionEvent, StateChangeEvent

_SYNTHETIC = frozenset({"executing_agent_id", "quality_score", "execution_id", "execution_path"})


@dataclasses.dataclass(frozen=True, kw_only=True)
class TaskSnapshot(Snapshot):
    id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    parent_task_id: uuid.UUID | None
    coordinator_agent_id: uuid.UUID | None
    created_by_agent_id: uuid.UUID | None
    delegation_depth: int
    title: str
    status: str
    task_type: str | None
    required_skills: dict | None
    difficulty: float | None
    domain_tags: dict | None
    # Synthetic fields — not columns on Task; passed explicitly by execute_task.
    executing_agent_id: uuid.UUID | None = dataclasses.field(default=None)
    quality_score: float | None = dataclasses.field(default=None)
    execution_id: uuid.UUID | None = dataclasses.field(default=None)
    execution_path: Literal["self_execute", "cfp", "decompose"] | None = dataclasses.field(default=None)

    @classmethod
    def from_domain(
        cls,
        model: object,
        *,
        executing_agent_id: uuid.UUID | None = None,
        quality_score: float | None = None,
        execution_id: uuid.UUID | None = None,
        execution_path: Literal["self_execute", "cfp", "decompose"] | None = None,
    ) -> TaskSnapshot:
        return cls(
            **{f.name: getattr(model, f.name) for f in dataclasses.fields(cls) if f.name not in _SYNTHETIC},
            executing_agent_id=executing_agent_id,
            quality_score=quality_score,
            execution_id=execution_id,
            execution_path=execution_path,
        )


@dataclasses.dataclass(kw_only=True)
class TaskCreatedEvent(StateActionEvent[TaskSnapshot]):
    workspace_id: uuid.UUID


@dataclasses.dataclass(kw_only=True)
class TaskUpdatedEvent(StateChangeEvent[TaskSnapshot]):
    workspace_id: uuid.UUID


@dataclasses.dataclass(kw_only=True)
class TaskDeletedEvent(StateActionEvent[TaskSnapshot]):
    workspace_id: uuid.UUID
