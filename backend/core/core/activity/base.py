from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.bus.common import DomainEvent

PublishFn = Callable[[DomainEvent], Awaitable[None]]