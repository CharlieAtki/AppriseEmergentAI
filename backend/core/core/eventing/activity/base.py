from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.eventing.bus import DomainEvent

PublishFn = Callable[[DomainEvent], Awaitable[None]]