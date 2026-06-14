"""Callable type aliases for the two publish surfaces in the event system.

``PublishFn`` — in-process, typed domain events
    Used by activity loggers (TaskActivityLogger, AgentActivityLogger). Accepts a
    DomainEvent subclass and delivers it to handlers registered on the same-process
    EventBus. Does not survive process restart. Injected as ``event_bus.apublish``.

``StreamPublishFn`` — cross-process, Redis Streams
    Used by TaskStreamLogger. Accepts a typed StreamEvent whose to_payload() and
    stream_key are used by RedisBus.apublish() for serialization and routing.
    Survives crash, delivers at-least-once. Injected as ``bus.apublish``.

Never mix the two: in-process handlers cannot receive stream events and vice versa.
Both use ``apublish`` as the method name — the distinction is the argument type:
DomainEvent for in-process, StreamEvent for cross-process.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from core.eventing.bus.common import DomainEvent, StreamEvent

PublishFn = Callable[[DomainEvent], Awaitable[list[asyncio.Task[None]]]]
StreamPublishFn = Callable[[StreamEvent], Awaitable[None]]
