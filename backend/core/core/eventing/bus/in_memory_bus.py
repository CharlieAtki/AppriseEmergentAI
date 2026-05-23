from __future__ import annotations

import asyncio
from typing import AsyncIterator


class InMemoryBus:
    """In-memory event bus — drop-in replacement for RedisBus in tests.

    Satisfies both BusProtocol (publish-only) and SubscribableBusProtocol
    (publish + subscribe + ack) structurally.

    Published events are stored in two places:
    - _published: append-only list per stream, for test assertions via published()
    - _queues: asyncio.Queue per stream, for reactive subscribe() delivery

    Test pattern:
        bus = InMemoryBus()
        await bus.publish("task.ws1.created", {"task_id": "t1"})
        assert bus.published("task.ws1.created") == [{"task_id": "t1"}]
    """

    def __init__(self) -> None:
        self._published: dict[str, list[dict]] = {}
        self._queues: dict[str, asyncio.Queue[dict]] = {}

    def _get_queue(self, stream: str) -> asyncio.Queue[dict]:
        if stream not in self._queues:
            self._queues[stream] = asyncio.Queue()
        return self._queues[stream]

    async def publish(self, stream: str, payload: dict) -> None:
        self._published.setdefault(stream, []).append(payload)
        await self._get_queue(stream).put(payload)

    async def subscribe(
        self,
        stream: str,
        group: str = "",
        consumer: str = "",
        *,
        batch_size: int = 10,
        block_ms: int = 1000,
    ) -> AsyncIterator[tuple[str, dict]]:
        """Yield (message_id, payload) from the in-memory queue for a stream.

        group, consumer, batch_size, and block_ms are accepted for interface
        compatibility with RedisBus but have no effect.
        """
        queue = self._get_queue(stream)
        i = 0
        while True:
            payload = await queue.get()
            yield str(i), payload
            i += 1

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        """No-op — no PEL concept in-memory."""

    def published(self, stream: str) -> list[dict]:
        """Return all events published to a stream (for test assertions)."""
        return list(self._published.get(stream, []))

    def clear(self) -> None:
        """Reset all state. Call between tests to prevent leakage."""
        self._published.clear()
        self._queues.clear()
