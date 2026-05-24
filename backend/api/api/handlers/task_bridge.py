from __future__ import annotations

from typing import TYPE_CHECKING

from core.eventing.bus.handlers import EventHandler
from core.eventing.events.stream_events import TaskCreatedStreamEvent

if TYPE_CHECKING:
    from core.eventing.bus.redis_bus import RedisBus
    from core.eventing.events.task_events import TaskCreatedEvent


class TaskCreatedRedisPublisher(EventHandler["TaskCreatedEvent"]):
    """Bridges in-process TaskCreatedEvent → Redis Streams TaskCreatedStreamEvent.

    Registered on the API's in-process EventBus so that when enrich_and_release
    fires task_logger.created(task), this handler forwards the event to Redis
    Streams where the worker's TaskStreamSubscriber picks it up for bidding.
    """

    def __init__(self, bus: RedisBus) -> None:
        self._bus = bus

    async def handle(self, event: TaskCreatedEvent) -> None:
        s = event.state
        await self._bus.apublish(TaskCreatedStreamEvent(
            task_id=s.id,
            workspace_id=s.workspace_id,
            organisation_id=s.organisation_id,
            required_skills=s.required_skills or {},
            difficulty=s.difficulty,
            task_type=s.task_type,
            domain_tags=s.domain_tags,
        ))
