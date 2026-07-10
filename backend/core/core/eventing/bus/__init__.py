from typing import TYPE_CHECKING

from core.eventing.bus.common import DomainEvent, Snapshot, StateActionEvent, StateChangeEvent
from core.eventing.bus.handlers import (
    EventHandler,
    ExternalEventSubscriber,
    Filtering,
    Retry,
    SyncEventHandler,
    SyncToAsync,
    Timeout,
)
from core.eventing.bus.in_memory_bus import InMemoryBus
from core.eventing.bus.in_process_bus import EventBus
from core.eventing.bus.protocols import BusProtocol, SubscribableBusProtocol

if TYPE_CHECKING:
    from core.eventing.bus.redis_bus import RedisBus


def __getattr__(name: str) -> object:
    # RedisBus is the only symbol in this package that pulls in redis.asyncio.
    # Deferring it keeps `core.eventing.bus.common` (and anything that imports
    # only from it) free of a redis dependency at import time — importing any
    # submodule of this package still executes this __init__, so eager imports
    # here would otherwise pull redis into every event-model import regardless
    # of which submodule was actually requested.
    if name == "RedisBus":
        from core.eventing.bus.redis_bus import RedisBus

        return RedisBus
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BusProtocol",
    "DomainEvent",
    "EventBus",
    "EventHandler",
    "ExternalEventSubscriber",
    "Filtering",
    "InMemoryBus",
    "RedisBus",
    "Retry",
    "Snapshot",
    "StateActionEvent",
    "StateChangeEvent",
    "SubscribableBusProtocol",
    "SyncEventHandler",
    "SyncToAsync",
    "Timeout",
]
