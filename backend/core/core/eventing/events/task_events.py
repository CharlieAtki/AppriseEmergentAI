from __future__ import annotations

import dataclasses
import uuid

from core.eventing.bus import Snapshot, StateActionEvent, StateChangeEvent


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
    executing_agent_id: uuid.UUID | None = dataclasses.field(default=None)

    @classmethod
    def from_domain(cls, model: object, *, executing_agent_id: uuid.UUID | None = None) -> TaskSnapshot:
        """Override to handle executing_agent_id, which is not a Task column.

        Pass executing_agent_id explicitly when constructing a snapshot inside
        execute_task where the executing agent is known. All other callers
        (decompose, rollup handler, CFP path, etc.) receive None by default.
        """
        return cls(
            **{f.name: getattr(model, f.name) for f in dataclasses.fields(cls) if f.name != "executing_agent_id"},
            executing_agent_id=executing_agent_id,
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
