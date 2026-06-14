from __future__ import annotations

from typing import TYPE_CHECKING

from core.eventing.activity.task_stream_logger import TaskStreamLogger
from core.eventing.bus.handlers import EventHandler

if TYPE_CHECKING:
    from core.eventing.events.task_events import TaskCreatedEvent


class TaskCreatedRedisPublisher(EventHandler["TaskCreatedEvent"]):
    """Bridges in-process TaskCreatedEvent → Redis Streams TaskCreatedStreamEvent.

    Registered on the API's in-process EventBus so that when enrich_and_release
    fires task_logger.created(task), this handler forwards the event to Redis
    Streams where the worker's TaskStreamSubscriber picks it up for bidding.

    Receives TaskStreamLogger (not RedisBus) — all event construction and
    bus access is delegated to the logger per CLAUDE.md eventing rules.
    """

    def __init__(self, stream_logger: TaskStreamLogger) -> None:
        self._stream_logger = stream_logger

    async def handle(self, event: TaskCreatedEvent) -> None:
        await self._stream_logger.task_created_from_snapshot(event.state)
