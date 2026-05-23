from __future__ import annotations

import dataclasses
import uuid

from core.bus.common import Snapshot, StateActionEvent, StateChangeEvent


@dataclasses.dataclass(frozen=True, kw_only=True)
class AgentSnapshot(Snapshot):
    id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    status: str
    skills: dict | None
    influence: float | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class AgentCreatedEvent(StateActionEvent[AgentSnapshot]):
    workspace_id: uuid.UUID


@dataclasses.dataclass(frozen=True, kw_only=True)
class AgentUpdatedEvent(StateChangeEvent[AgentSnapshot]):
    workspace_id: uuid.UUID


@dataclasses.dataclass(frozen=True, kw_only=True)
class AgentDeletedEvent(StateActionEvent[AgentSnapshot]):
    workspace_id: uuid.UUID
