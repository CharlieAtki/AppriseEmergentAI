from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from core.eventing.bus.common import DomainEvent
from core.eventing.bus.handlers import EventHandler, ExternalEventSubscriber

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class EventBus:
    """In-process async event bus with MRO-based handler routing.

    Handlers bound to a base event class automatically receive all subclass
    events — subscribe once to a category, handle every variant.

    All handlers run fire-and-forget. Use :class:`~core.bus.handlers.Retry`,
    :class:`~core.bus.handlers.Timeout`, and
    :class:`~core.bus.handlers.Filtering` to compose error-handling behaviour
    at the registration site rather than inside handler bodies.

    Construct with the running event loop::

        loop = asyncio.get_running_loop()
        bus = EventBus(loop=loop)

    Use :meth:`apublish` from async callers (FastAPI endpoints, worker jobs).
    Use :meth:`publish` only from synchronous callers running on a different
    thread from the event loop.
    """

    def __init__(self, *, loop: asyncio.AbstractEventLoop) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)
        self._subscribers: list[ExternalEventSubscriber] = []
        self._loop = loop
        # asyncio.ensure_future only weak-refs the returned Task; without a strong
        # reference a background handler can be GC'd mid-execution. We pin tasks
        # here and let the done-callback evict them when they finish.
        self._pending_tasks: set[asyncio.Task] = set()

    def bind(
        self,
        event_types: type[DomainEvent] | Sequence[type[DomainEvent]],
        handler: EventHandler,
    ) -> None:
        """Register a fire-and-forget async handler for one or more event types."""
        if isinstance(event_types, type):
            event_types = [event_types]
        for event_type in event_types:
            self._handlers[event_type].append(handler)
        logger.debug("Bound %s to %s", repr(handler), [t.__name__ for t in event_types])

    def subscribe(self, subscriber: ExternalEventSubscriber) -> None:
        """Register an external subscriber. Call before :meth:`start_subscribers`."""
        self._subscribers.append(subscriber)
        logger.debug("Registered subscriber %s", type(subscriber).__name__)

    def publish(self, event: DomainEvent) -> None:
        """Dispatch handlers from a synchronous caller on a different thread.

        Uses :func:`asyncio.run_coroutine_threadsafe` to schedule each handler
        on the bound event loop. Prefer :meth:`apublish` from async callers.
        """
        for handler in self._handlers_for(event):
            asyncio.run_coroutine_threadsafe(self._handle_safely(handler, event), self._loop)

    async def apublish(self, event: DomainEvent) -> list[asyncio.Task[None]]:
        """Dispatch handlers from an async caller. Returns the scheduled tasks.

        Schedules all matching handlers fire-and-forget and returns the
        asyncio.Task objects created. Callers that need to know when handlers
        have finished (e.g. StreamSubscriber, to defer the Redis Stream ACK)
        can await the returned tasks with asyncio.gather. Callers that do not
        need to wait simply discard the return value.

        Exceptions are caught per handler by _handle_safely and never propagate.
        """
        tasks: list[asyncio.Task[None]] = []
        for handler in self._handlers_for(event):
            task = asyncio.ensure_future(self._handle_safely(handler, event))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
            tasks.append(task)
        return tasks

    def _handlers_for(self, event: DomainEvent) -> list[EventHandler]:
        return [
            handler
            for cls in type(event).mro()
            if cls is not object
            for handler in self._handlers.get(cls, [])
        ]

    @staticmethod
    async def _handle_safely(handler: EventHandler, event: DomainEvent) -> None:
        try:
            await handler.handle(event)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Background handler %s failed on event %s (id=%s)",
                repr(handler),
                type(event).__name__,
                event.event_id,
            )

    async def drain_pending(self, *, timeout: float | None = None) -> None:
        """Await all in-flight fire-and-forget tasks scheduled via :meth:`apublish`.

        Call at shutdown before stopping subscribers to prevent tasks from being
        cancelled mid-execution when the event loop stops.
        """
        if not self._pending_tasks:
            return
        await asyncio.wait(list(self._pending_tasks), timeout=timeout)

    async def start_subscribers(self) -> None:
        for subscriber in self._subscribers:
            await subscriber.start()

    async def stop_subscribers(self) -> None:
        for subscriber in self._subscribers:
            try:
                await subscriber.stop()
            except Exception:  # noqa: BLE001
                logger.exception("Error stopping subscriber %s", type(subscriber).__name__)