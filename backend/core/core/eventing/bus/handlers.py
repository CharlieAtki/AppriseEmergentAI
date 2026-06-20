from __future__ import annotations

import abc
import asyncio
from typing import TYPE_CHECKING

from core.utils.retry import retry_async

if TYPE_CHECKING:
    from collections.abc import Callable


class SyncEventHandler[E](abc.ABC):
    @abc.abstractmethod
    def handle(self, event: E) -> None: ...


class EventHandler[E](abc.ABC):
    @abc.abstractmethod
    async def handle(self, event: E) -> None: ...


class ExternalEventSubscriber[E](abc.ABC):
    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def stop(self) -> None: ...


class SyncToAsync[E](EventHandler[E]):
    """Adapts a :class:`SyncEventHandler` to the :class:`EventHandler` interface.

    Runs the synchronous handler in a thread executor via
    :func:`asyncio.to_thread`, making it compatible with :meth:`EventBus.bind`
    and the composable wrapper chain::

        bus.bind(AgentDeletedEvent, SyncToAsync(ComplianceHandler()))

        bus.bind(AgentDeletedEvent, Retry(SyncToAsync(ComplianceHandler()),
            retry_on=(OperationalError,)))
    """

    def __init__(self, handler: SyncEventHandler[E]) -> None:
        self._handler = handler

    async def handle(self, event: E) -> None:
        await asyncio.to_thread(self._handler.handle, event)

    def __repr__(self) -> str:
        return f"SyncToAsync({type(self._handler).__name__})"


class Retry[E](EventHandler[E]):
    """Wraps an :class:`EventHandler` with configurable retry-on-failure behaviour.

    Retries up to *max_attempts* times with exponential backoff
    (``backoff * 2 ** attempt`` seconds between attempts).

    Exception dispatch:

    - Matches *fatal_on* first: re-raised immediately, no retry.
    - Matches *retry_on*: retried. After the final attempt, re-raised.
    - Matches neither: propagates immediately — same effect as *fatal_on*.

    Compose with :class:`SyncToAsync` for synchronous handlers::

        bus.bind(AgentDeletedEvent, Retry(SyncToAsync(ComplianceHandler()),
            retry_on=(OperationalError, TimeoutError),
        ))
    """

    def __init__(
        self,
        handler: EventHandler[E],
        *,
        max_attempts: int = 3,
        retry_on: tuple[type[Exception], ...] = (Exception,),
        fatal_on: tuple[type[Exception], ...] = (),
        backoff: float = 1.0,
    ) -> None:
        self._handler = handler
        self._max_attempts = max_attempts
        self._retry_on = retry_on
        self._fatal_on = fatal_on
        self._backoff = backoff

    async def handle(self, event: E) -> None:
        def is_retryable(exc: BaseException) -> bool:
            if isinstance(exc, self._fatal_on):
                return False
            return isinstance(exc, self._retry_on)

        await retry_async(
            fn=lambda: self._handler.handle(event),
            is_retryable=is_retryable,
            max_attempts=self._max_attempts,
            backoff=self._backoff,
        )

    def __repr__(self) -> str:
        return f"Retry({self._handler!r}, max={self._max_attempts})"


class Filtering[E](EventHandler[E]):
    """Wraps an :class:`EventHandler` with a predicate gate.

    The handler only runs when ``predicate(event)`` is truthy. Use to move
    filter conditions out of handler bodies and into the registration site::

        bus.bind(AgentDeletedEvent, Filtering(
            SyncToAsync(ComplianceHandler()),
            predicate=lambda e: get_config().governance.is_eqty,
        ))
    """

    def __init__(self, handler: EventHandler[E], *, predicate: Callable[[E], bool]) -> None:
        self._handler = handler
        self._predicate = predicate

    async def handle(self, event: E) -> None:
        if self._predicate(event):
            await self._handler.handle(event)

    def __repr__(self) -> str:
        return f"Filtering({self._handler!r})"


class Timeout[E](EventHandler[E]):
    """Wraps an :class:`EventHandler` with an asyncio timeout.

    Raises :exc:`TimeoutError` if the handler exceeds *seconds*. Composes
    with :class:`Retry` to retry timed-out handlers::

        bus.bind(MyEvent, Retry(Timeout(MyHandler(), seconds=30),
            retry_on=(TimeoutError,)))

    Note: when wrapping :class:`SyncToAsync`, the timeout cancels the wait
    but not the underlying thread — the sync work continues in the background.
    """

    def __init__(self, handler: EventHandler[E], *, seconds: float) -> None:
        self._handler = handler
        self._seconds = seconds

    async def handle(self, event: E) -> None:
        await asyncio.wait_for(self._handler.handle(event), timeout=self._seconds)

    def __repr__(self) -> str:
        return f"Timeout({self._handler!r}, seconds={self._seconds})"
