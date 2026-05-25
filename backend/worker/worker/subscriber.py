from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field

from core.eventing.bus.common import StreamEvent
from core.eventing.bus.handlers import ExternalEventSubscriber
from core.eventing.bus.in_process_bus import EventBus
from core.eventing.bus.redis_bus import RedisBus
from core.eventing.events.stream_events import (
    CfpIssuedStreamEvent,
    TaskCompletedStreamEvent,
    TaskCreatedStreamEvent,
)

logger = logging.getLogger(__name__)

_STREAM = "stream:task"
_GROUP = "worker-group"


@dataclass
class TaskStreamSubscriber(ExternalEventSubscriber):
    """Bridges the Redis Streams transport into the in-process :class:`EventBus`.

    Consumes messages from ``"stream:task"`` via a Redis Streams consumer group
    and fires typed domain events onto the in-process ``EventBus``. Business
    logic lives in :class:`~core.eventing.bus.handlers.EventHandler`
    implementations bound to those event types — this class knows nothing about
    bidding, social memory, or any other handler concern.

    Lifecycle is managed by :meth:`EventBus.start_subscribers` /
    :meth:`EventBus.stop_subscribers`, which are called from the ARQ startup and
    shutdown hooks:

    - :meth:`start` spawns the consumer loop as a named :class:`asyncio.Task`.
    - :meth:`stop` cancels it and awaits clean exit, suppressing
      :exc:`asyncio.CancelledError`.

    ``consumer`` must be unique per worker process to prevent two processes
    reading from the same consumer group slot. Use ``f"worker-{os.getpid()}"``
    at registration time.

    At-least-once delivery is guaranteed by the Redis Streams PEL: if a worker
    crashes mid-handler, the message remains in the PEL and will be redelivered
    to the next consumer that calls ``XREADGROUP``. ``ack`` is called in the
    ``finally`` block after :meth:`EventBus.apublish` schedules all handlers
    fire-and-forget — the ack does not wait for handlers to complete.
    """

    bus: RedisBus
    event_bus: EventBus
    consumer: str

    _task: asyncio.Task | None = field(default=None, init=False, repr=False)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="task-stream-subscriber")
        logger.info("task subscriber started (consumer=%s)", self.consumer)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("task subscriber stopped (consumer=%s)", self.consumer)

    async def _run(self) -> None:
        """Long-running consumer loop. Never raises — logs and continues on errors."""
        async for msg_id, payload in self.bus.subscribe(_STREAM, _GROUP, self.consumer):
            try:
                event = _parse_stream_event(payload)
                if event is not None:
                    await self.event_bus.apublish(event)
            except Exception:
                logger.exception("subscriber error on message %s: %r", msg_id, payload)
            finally:
                await self.bus.ack(_STREAM, _GROUP, msg_id)

# Registry maps event_type discriminator → StreamEvent subclass.
# Adding a new event type: define the class in stream_events.py and add one line here.
# No other files need to change.
_REGISTRY: dict[str, type[StreamEvent]] = {
    "task.created":   TaskCreatedStreamEvent,
    "task.completed": TaskCompletedStreamEvent,
}

_CFP_STREAM = "stream:cfp"
_CFP_GROUP = "cfp-group"

_CFP_REGISTRY: dict[str, type[StreamEvent]] = {
    "cfp.issued": CfpIssuedStreamEvent,
}


def _parse_stream_event(payload: dict, registry: dict[str, type[StreamEvent]] | None = None) -> StreamEvent | None:
    """Deserialise a Redis Stream payload into a typed StreamEvent.

    Routes via ``registry`` keyed on ``event_type``. Returns ``None`` for unknown
    types so the caller can ack-and-skip without crashing the consumer loop.
    Unknown types are logged at DEBUG — not WARNING — to avoid noise from future
    event types that older worker versions don't yet handle.

    Missing required keys (e.g. malformed ``task_id``) will raise and be caught
    by the caller's ``except`` block, which logs at ERROR and acks the message
    to avoid it blocking the PEL indefinitely.

    Deserialization logic lives on each StreamEvent class (from_payload), so
    this function stays stable as event fields evolve.
    """
    resolved = registry if registry is not None else _REGISTRY
    event_type = payload.get("event_type", "")
    cls = resolved.get(event_type)
    if cls is None:
        logger.debug("subscriber: unknown event_type=%r, skipping", event_type)
        return None
    return cls.from_payload(payload)


@dataclass
class CfpStreamSubscriber(ExternalEventSubscriber):
    """Bridges the ``stream:cfp`` Redis Stream into the in-process :class:`EventBus`.

    Mirrors :class:`TaskStreamSubscriber` exactly: consumes from ``"stream:cfp"``
    via consumer group ``"cfp-group"``, deserializes via ``_CFP_REGISTRY``, and
    fires typed events onto the in-process ``EventBus``. :class:`CfpHandler` is
    bound to :class:`CfpIssuedStreamEvent` and performs the actual bid logic.

    Uses a separate consumer group (``"cfp-group"``) from the task subscriber so
    the two streams are consumed independently and neither blocks the other.
    """

    bus: RedisBus
    event_bus: EventBus
    consumer: str

    _task: asyncio.Task | None = field(default=None, init=False, repr=False)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="cfp-stream-subscriber")
        logger.info("CFP subscriber started (consumer=%s)", self.consumer)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("CFP subscriber stopped (consumer=%s)", self.consumer)

    async def _run(self) -> None:
        async for msg_id, payload in self.bus.subscribe(_CFP_STREAM, _CFP_GROUP, self.consumer):
            try:
                event = _parse_stream_event(payload, _CFP_REGISTRY)
                if event is not None:
                    await self.event_bus.apublish(event)
            except Exception:
                logger.exception("CFP subscriber error on message %s: %r", msg_id, payload)
            finally:
                await self.bus.ack(_CFP_STREAM, _CFP_GROUP, msg_id)
