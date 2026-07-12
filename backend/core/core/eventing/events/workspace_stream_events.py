"""Typed dashboard events published over Redis Pub/Sub by WorkspaceStreamLogger.

Deliberately not StreamEvent subclasses: StreamEvent's contract (stream_key,
from_payload) is for Redis Streams' durable, subscriber-side-reconstructed
transport (see core/eventing/bus/common.py). These events are Pub/Sub only —
fire-and-forget straight to a browser's WebSocket — so there is no Python-side
subscriber to reconstruct from a payload; the only consumer is the frontend's
WorkspaceEvent Zod union. Forcing a stream_key/from_payload here would be two
permanently-dead members, not adherence to the pattern.

Each class owns its event_type discriminator and to_payload() wire shaping —
one definition per event, matching TaskCreatedStreamEvent's discipline of no
downstream dict-spelunking or ad hoc dict literals scattered across callers.

Adding a dashboard event: define a class here, add a matching method to
WorkspaceStreamLogger, add the matching Zod schema to the frontend's
WorkspaceEvent union. No other files need to change.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


class WorkspaceStreamEvent(Protocol):
    """Structural contract — any event type WorkspaceStreamLogger can publish."""

    def to_payload(self) -> dict[str, object]: ...


@dataclass(frozen=True, kw_only=True)
class TaskExecutingEvent:
    task_id: uuid.UUID
    agent_id: uuid.UUID

    def to_payload(self) -> dict[str, object]:
        return {
            "type": "task.executing",
            "task_id": str(self.task_id),
            "agent_id": str(self.agent_id),
        }


@dataclass(frozen=True, kw_only=True)
class TaskCreatedEvent:
    task_id: uuid.UUID
    title: str
    status: str

    def to_payload(self) -> dict[str, object]:
        return {
            "type": "task.created",
            "task_id": str(self.task_id),
            "title": self.title,
            "status": self.status,
        }


@dataclass(frozen=True, kw_only=True)
class TaskFailedEvent:
    task_id: uuid.UUID
    agent_id: uuid.UUID
    error_message: str

    def to_payload(self) -> dict[str, object]:
        return {
            "type": "task.failed",
            "task_id": str(self.task_id),
            "agent_id": str(self.agent_id),
            "error_message": self.error_message,
        }


@dataclass(frozen=True, kw_only=True)
class TaskCompletedEvent:
    task_id: uuid.UUID
    agent_id: uuid.UUID
    quality_score: float

    def to_payload(self) -> dict[str, object]:
        return {
            "type": "task.completed",
            "task_id": str(self.task_id),
            "agent_id": str(self.agent_id),
            "quality_score": self.quality_score,
        }


@dataclass(frozen=True, kw_only=True)
class AgentSkillUpdatedEvent:
    agent_id: uuid.UUID
    skill_deltas: Mapping[str, float]
    new_influence: float

    def to_payload(self) -> dict[str, object]:
        return {
            "type": "agent.skill_updated",
            "agent_id": str(self.agent_id),
            "skill_deltas": dict(self.skill_deltas),
            "new_influence": self.new_influence,
        }


@dataclass(frozen=True, kw_only=True)
class EmergenceDetectedEvent:
    gini_coefficient: float
    hub_agent_id: uuid.UUID

    def to_payload(self) -> dict[str, object]:
        return {
            "type": "emergence.detected",
            "gini_coefficient": self.gini_coefficient,
            "hub_agent_id": str(self.hub_agent_id),
        }
