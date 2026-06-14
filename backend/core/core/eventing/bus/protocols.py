from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class BusProtocol(Protocol):
    """Publish-only bus interface. Satisfied by RedisBus and InMemoryBus."""

    async def publish(self, stream: str, payload: dict) -> None: ...


class SubscribableBusProtocol(BusProtocol, Protocol):
    """Full publish + subscribe interface. Worker types against this."""

    def subscribe(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        batch_size: int = 10,
        block_ms: int = 1000,
    ) -> AsyncIterator[tuple[str, dict]]: ...

    async def ack(self, stream: str, group: str, message_id: str) -> None: ...
