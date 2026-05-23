from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable

from core.bus.common import DomainEvent

PublishFn = Callable[[DomainEvent], Awaitable[None]]


class ActivityLogger(abc.ABC):
    """Base for all activity logger facades.

    Subclasses receive a publish callable at construction — never the bus directly.
    Their only job is to construct the correct event from a domain model and forward it.
    """

    def __init__(self, publish: PublishFn) -> None:
        self._publish = publish
