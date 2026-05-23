from __future__ import annotations

import dataclasses
import uuid

from core.eventing.bus.common import DomainEvent


@dataclasses.dataclass(kw_only=True)
class TaskCreatedStreamEvent(DomainEvent):
    """Fired when a ``task.created`` message is consumed off Redis Streams.

    Carries only the fields needed for algorithmic bidding. Distinct from
    :class:`~core.eventing.events.task_events.TaskCreatedEvent` (in-process,
    full ORM snapshot) — this event crosses a process boundary and cannot carry
    an ORM-backed snapshot. The payload is limited to the coordination data
    published by :func:`~core.coordination.decompose.decompose_and_publish`,
    :func:`~worker.jobs.execute_task._release_to_pool`, and the API task router.

    Published by :class:`~worker.subscriber.TaskStreamSubscriber` after
    deserialising the Redis payload. Consumed by
    :class:`~worker.handlers.bidding.TaskBiddingHandler` to score agents and
    enqueue ``execute_task`` jobs.
    """

    task_id: uuid.UUID
    workspace_id: uuid.UUID
    required_skills: dict
    domain_tags: dict | None = None


@dataclasses.dataclass(kw_only=True)
class TaskCompletedStreamEvent(DomainEvent):
    """Fired when a ``task.completed`` message is consumed off Redis Streams.

    Carries only the fields needed for social memory writes. Published by
    :class:`~worker.subscriber.TaskStreamSubscriber` after deserialising the
    Redis payload emitted by Phase 7 of ``execute_task``. Consumed by
    :class:`~worker.handlers.social_memory.SocialMemoryHandler` to fan out
    peer observations to Qdrant.
    """

    task_id: uuid.UUID
    workspace_id: uuid.UUID
    completing_agent_id: uuid.UUID
    quality_score: float
    task_type: str
