from __future__ import annotations

import abc
from typing import Generic, TypeVar

from core.bus.common import DomainEvent

E = TypeVar("E", bound=DomainEvent)


class AsyncEventHandler(abc.ABC, Generic[E]):
    @abc.abstractmethod
    async def handle(self, event: E) -> None: ...