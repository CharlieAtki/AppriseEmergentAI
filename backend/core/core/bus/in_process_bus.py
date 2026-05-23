from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine, Sequence
from typing import Any

from core.bus.common import DomainEvent
from core.bus.handlers import AsyncEventHandler

logger = logging.getLogger(__name__)


class InProcessBus:
    """In-process async event bus with MRO-based handler routing.

    Handlers bound to a base event class automatically receive all subclass
    events — subscribe once to a category, handle every variant.

    Two registration modes:
    - bind()             fire-and-forget via asyncio.create_task, errors logged silently
    - bind_transactional()  awaited before publish() returns, errors propagate to caller
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[AsyncEventHandler]] = {}
        self._transactional: dict[type[DomainEvent], list[AsyncEventHandler]] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()

    def bind(
        self,
        event_types: type[DomainEvent] | Sequence[type[DomainEvent]],
        handler: AsyncEventHandler,
    ) -> None:
        for event_type in _normalise(event_types):
            self._handlers.setdefault(event_type, []).append(handler)

    def bind_transactional(
        self,
        event_types: type[DomainEvent] | Sequence[type[DomainEvent]],
        handler: AsyncEventHandler,
    ) -> None:
        for event_type in _normalise(event_types):
            self._transactional.setdefault(event_type, []).append(handler)

    async def publish(self, event: DomainEvent) -> None:
        mro = type(event).mro()

        for cls in mro:
            if cls is object:
                continue
            for handler in self._transactional.get(cls, []):  # type: ignore[arg-type]
                await handler.handle(event)

        for cls in mro:
            if cls is object:
                continue
            for handler in self._handlers.get(cls, []):  # type: ignore[arg-type]
                self._schedule(self._safe_handle(handler, event))

    async def wait_pending(self) -> None:
        """Drain all in-flight fire-and-forget tasks. Call at shutdown to avoid silent cancellation."""
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

    def _schedule(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    @staticmethod
    async def _safe_handle(handler: AsyncEventHandler, event: DomainEvent) -> None:
        try:
            await handler.handle(event)
        except Exception:  # noqa: BLE001 — fire-and-forget boundary, must not propagate
            logger.exception(
                "Handler %s failed for %s",
                type(handler).__name__,
                type(event).__name__,
            )


def _normalise(
    event_types: type[DomainEvent] | Sequence[type[DomainEvent]],
) -> Sequence[type[DomainEvent]]:
    if isinstance(event_types, type):
        return (event_types,)
    return event_types