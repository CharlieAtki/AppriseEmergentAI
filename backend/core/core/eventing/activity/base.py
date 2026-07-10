"""Callable type aliases for the three publish surfaces in the event system.

``PublishFn`` — in-process, typed domain events
    Used by activity loggers (TaskActivityLogger, AgentActivityLogger). Accepts a
    DomainEvent subclass and delivers it to handlers registered on the same-process
    EventBus. Does not survive process restart. Injected as ``event_bus.apublish``.

``StreamPublishFn`` — cross-process, Redis Streams
    Used by TaskStreamLogger. Accepts a typed StreamEvent whose to_payload() and
    stream_key are used by RedisBus.apublish() for serialization and routing.
    Survives crash, delivers at-least-once. Injected as ``bus.apublish``.

``PubSubPublishFn`` — cross-process, Redis Pub/Sub
    Used by WorkspaceStreamLogger and JobSpan.emit(). Raw (channel, payload-dict) —
    no consumer group, no durability; a message published with no subscriber is
    lost. Used only for fan-out to live WebSocket viewers, never for coordination
    state. Takes a plain ``Mapping`` rather than a typed event because it's shared
    by two producers with different payload shapes: WorkspaceStreamLogger's closed
    set of typed dashboard events, and JobSpan.emit()'s deliberately open-ended
    tracing dicts. The concrete implementation (make_centrifugo_publish) owns
    turning the dict into wire JSON — callers never pre-serialize.

Never mix these: in-process handlers cannot receive stream or pub/sub events and
vice versa. ``PublishFn``/``StreamPublishFn`` both use ``apublish`` as the method
name — the distinction is the argument type: DomainEvent for in-process, StreamEvent
for cross-process.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping

from core.eventing.bus.common import DomainEvent, StreamEvent

PublishFn = Callable[[DomainEvent], Awaitable[list[asyncio.Task[None]]]]
StreamPublishFn = Callable[[StreamEvent], Awaitable[None]]
PubSubPublishFn = Callable[[str, Mapping[str, object]], Awaitable[None]]
