from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.eventing.activity.base import PublishFn
from core.eventing.bus.common import StreamEvent
from core.eventing.bus.handlers import ExternalEventSubscriber
from core.eventing.events.stream_events import (
    CfpIssuedStreamEvent,
    TaskCompletedStreamEvent,
    TaskCreatedStreamEvent,
)

if TYPE_CHECKING:
    from core.eventing.bus.protocols import SubscribableBusProtocol

logger = logging.getLogger(__name__)

# Registry maps event_type discriminator → StreamEvent subclass.
# Adding a new event type: define the class in stream_events.py and add one entry here.
# No other files need to change.
TASK_STREAM_REGISTRY: Mapping[str, type[StreamEvent]] = {
    "task.created":   TaskCreatedStreamEvent,
    "task.completed": TaskCompletedStreamEvent,
}

CFP_STREAM_REGISTRY: Mapping[str, type[StreamEvent]] = {
    "cfp.issued": CfpIssuedStreamEvent,
}


def _parse_stream_event(
    payload: dict[str, Any],
    registry: Mapping[str, type[StreamEvent]],
) -> StreamEvent | None:
    """Deserialise a Redis Stream payload into a typed StreamEvent.

    Routes via ``registry`` keyed on ``event_type``. Returns ``None`` for unknown
    types so the caller can ack-and-skip without crashing the consumer loop.
    Unknown types are logged at DEBUG — not WARNING — to avoid noise from future
    event types that older worker versions don't yet handle.

    Missing required keys (e.g. malformed ``task_id``) will raise and be caught
    by the caller's ``except`` block, which logs at ERROR and acks the message
    to avoid it blocking the PEL indefinitely.

    Deserialisation logic lives on each StreamEvent class (from_payload), so
    this function stays stable as event fields evolve.
    """
    event_type = payload.get("event_type", "")
    cls = registry.get(event_type)
    if cls is None:
        logger.debug("subscriber: unknown event_type=%r, skipping", event_type)
        return None
    return cls.from_payload(payload)


@dataclass
class StreamSubscriber(ExternalEventSubscriber):
    """Bridges one Redis Stream into the in-process event bus.

    Consumes messages from ``stream`` via a Redis Streams consumer group and
    fires typed domain events via the ``publish`` callable. Business logic lives
    in :class:`~core.eventing.bus.handlers.EventHandler` implementations bound
    to those event types — this class knows nothing about bidding, memory, or
    any other handler concern.

    ``publish`` is ``EventBus.apublish`` — injected as a narrow callable rather
    than the full ``EventBus`` so the subscriber has no dependency on the bus
    implementation.

    ``registry`` maps the ``event_type`` discriminator field to the
    ``StreamEvent`` subclass responsible for deserialising that message. Add new
    event types by extending the registry at the call site — no change needed here.

    Lifecycle is managed by :meth:`EventBus.start_subscribers` /
    :meth:`EventBus.stop_subscribers`, called from the ARQ startup and shutdown
    hooks:

    - :meth:`start` spawns the consumer loop as a named :class:`asyncio.Task`.
    - :meth:`stop` cancels it and awaits clean exit, suppressing
      :exc:`asyncio.CancelledError`.

    ``consumer`` must be unique per worker process to prevent two processes
    reading from the same consumer group slot. Use ``f"worker-{os.getpid()}"``
    at registration time.

    At-least-once delivery is guaranteed by the Redis Streams PEL: if a worker
    crashes mid-handler, the message remains in the PEL and will be redelivered
    to the next consumer that calls ``XREADGROUP``. ``ack`` is called in the
    ``finally`` block after ``publish`` schedules all handlers fire-and-forget —
    the ack does not wait for handlers to complete.
    """

    bus:      SubscribableBusProtocol
    publish:  PublishFn
    stream:   str
    group:    str
    consumer: str
    registry: Mapping[str, type[StreamEvent]]
    name:     str  # used for task naming and log messages

    _task: asyncio.Task | None = field(default=None, init=False, repr=False)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"{self.name}-subscriber")
        logger.info("%s subscriber started (consumer=%s)", self.name, self.consumer)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("%s subscriber stopped (consumer=%s)", self.name, self.consumer)

    async def _run(self) -> None:
        """Long-running consumer loop. Never raises — logs and continues on errors."""
        async for msg_id, payload in self.bus.subscribe(self.stream, self.group, self.consumer):
            try:
                event = _parse_stream_event(payload, self.registry)
                if event is not None:
                    await self.publish(event)
            except Exception:
                logger.exception(
                    "%s subscriber error on message %s: %r", self.name, msg_id, payload
                )
            finally:
                await self.bus.ack(self.stream, self.group, msg_id)
