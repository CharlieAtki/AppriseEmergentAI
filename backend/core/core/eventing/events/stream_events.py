"""Cross-process stream event types for Redis Streams transport.

Each class is the single source of truth for one event type:
    - field definitions (what data crosses the wire)
    - stream_key (which Redis stream to publish to)
    - event_type (discriminator string for subscriber routing)
    - to_payload() (serialization — called by RedisBus.apublish)
    - from_payload() (deserialization — called by _parse_stream_event in subscriber.py)

Consumers of each event type:
    TaskCreatedStreamEvent   → TaskBiddingHandler  (worker/handlers/bidding.py)
    TaskCompletedStreamEvent → SocialMemoryHandler (worker/handlers/social_memory.py)
    CfpIssuedStreamEvent     → CfpHandler          (worker/handlers/cfp.py)

Adding a new event type:
    1. Define the class here (extend StreamEvent, implement all four members).
    2. Add one entry to _REGISTRY in worker/subscriber.py.
    No other files need to change.

Changing a field:
    Change it here only. to_payload() and from_payload() are colocated so
    publisher and subscriber stay in sync automatically.
"""
from __future__ import annotations

import dataclasses
import uuid

from core.eventing.bus.common import StreamEvent


@dataclasses.dataclass(kw_only=True)
class TaskCreatedStreamEvent(StreamEvent):
    """Fired when a task becomes available for bidding.

    Published by TaskStreamLogger.task_created() from two paths:
    - decompose_and_publish() — once per subtask after flush
    - _release_to_pool()      — when a CFP agent returns a task to "open"

    Consumer: TaskBiddingHandler scores agents against required_skills and
    domain_tags, wins a Redis SETNX reservation, and enqueues execute_task.

    organisation_id and task_type are included for future routing/audit use;
    the current bidding handler does not use them.
    """

    task_id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    required_skills: dict
    difficulty: float | None = None
    task_type: str | None = None
    domain_tags: dict | None = None

    @property
    def stream_key(self) -> str:
        return "stream:task"

    @property
    def event_type(self) -> str:
        return "task.created"

    def to_payload(self) -> dict:
        return {
            "event_type":      self.event_type,
            "event_id":        str(self.event_id),
            "task_id":         str(self.task_id),
            "workspace_id":    str(self.workspace_id),
            "organisation_id": str(self.organisation_id),
            "required_skills": self.required_skills,
            "difficulty":      self.difficulty,
            "task_type":       self.task_type,
            "domain_tags":     self.domain_tags or {},
        }

    @classmethod
    def from_payload(cls, payload: dict) -> TaskCreatedStreamEvent:
        return cls(
            task_id=uuid.UUID(payload["task_id"]),
            workspace_id=uuid.UUID(payload["workspace_id"]),
            organisation_id=uuid.UUID(payload["organisation_id"]),
            required_skills=payload.get("required_skills") or {},
            difficulty=float(payload["difficulty"]) if payload.get("difficulty") is not None else None,
            task_type=payload.get("task_type"),
            domain_tags=payload.get("domain_tags"),
        )


@dataclasses.dataclass(kw_only=True)
class TaskCompletedStreamEvent(StreamEvent):
    """Fired when an agent successfully self-executes a task.

    Published by TaskStreamLogger.task_completed() from execute_task Phase 7,
    after Phase 6 (write results) has committed — the task is "completed" in
    the DB before this event fires.

    Consumer: SocialMemoryHandler fans out peer observations to Qdrant so agents
    build social knowledge of who completed what and at what quality.
    """

    task_id: uuid.UUID
    workspace_id: uuid.UUID
    completing_agent_id: uuid.UUID
    quality_score: float
    task_type: str

    @property
    def stream_key(self) -> str:
        return "stream:task"

    @property
    def event_type(self) -> str:
        return "task.completed"

    def to_payload(self) -> dict:
        return {
            "event_type":          self.event_type,
            "event_id":            str(self.event_id),
            "task_id":             str(self.task_id),
            "workspace_id":        str(self.workspace_id),
            "completing_agent_id": str(self.completing_agent_id),
            "quality_score":       self.quality_score,
            "task_type":           self.task_type,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> TaskCompletedStreamEvent:
        return cls(
            task_id=uuid.UUID(payload["task_id"]),
            workspace_id=uuid.UUID(payload["workspace_id"]),
            completing_agent_id=uuid.UUID(payload["completing_agent_id"]),
            quality_score=float(payload.get("quality_score", 0.5)),
            task_type=str(payload.get("task_type", "general")),
        )


@dataclasses.dataclass(kw_only=True)
class CfpIssuedStreamEvent(StreamEvent):
    """Fired when an agent issues a Call for Proposals for a task.

    Published to ``"stream:cfp"`` (not workspace-scoped, matching the ``stream:task``
    convention). Workspace isolation is enforced by the SETNX reservation key
    (``reservation:{workspace_id}:{task_id}``) and handler-level workspace filtering,
    not the stream key. ``initiating_agent_id`` identifies the agent that chose to
    route; ``coordinator_agent_id`` is the grandparent coordinator if this task was
    itself part of a prior decomposition (may be None).
    """

    task_id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    initiating_agent_id: uuid.UUID
    coordinator_agent_id: uuid.UUID | None
    required_skills: dict
    difficulty: float | None
    task_type: str | None
    domain_tags: dict | None = None

    @property
    def stream_key(self) -> str:
        return "stream:cfp"

    @property
    def event_type(self) -> str:
        return "cfp.issued"

    def to_payload(self) -> dict:
        return {
            "event_type":           self.event_type,
            "event_id":             str(self.event_id),
            "task_id":              str(self.task_id),
            "workspace_id":         str(self.workspace_id),
            "organisation_id":      str(self.organisation_id),
            "initiating_agent_id":  str(self.initiating_agent_id),
            "coordinator_agent_id": str(self.coordinator_agent_id) if self.coordinator_agent_id else None,
            "required_skills":      self.required_skills,
            "difficulty":           self.difficulty,
            "task_type":            self.task_type,
            "domain_tags":          self.domain_tags or {},
        }

    @classmethod
    def from_payload(cls, payload: dict) -> CfpIssuedStreamEvent:
        coord = payload.get("coordinator_agent_id")
        return cls(
            task_id=uuid.UUID(payload["task_id"]),
            workspace_id=uuid.UUID(payload["workspace_id"]),
            organisation_id=uuid.UUID(payload["organisation_id"]),
            initiating_agent_id=uuid.UUID(payload["initiating_agent_id"]),
            coordinator_agent_id=uuid.UUID(coord) if coord else None,
            required_skills=payload.get("required_skills") or {},
            difficulty=float(payload["difficulty"]) if payload.get("difficulty") is not None else None,
            task_type=payload.get("task_type"),
            domain_tags=payload.get("domain_tags"),
        )
