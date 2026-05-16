from __future__ import annotations

import json
from typing import AsyncIterator

from redis.asyncio import Redis
from redis.exceptions import ResponseError

# ToDo: Need to wire up ReisBus - Currently using InMemoryBus for testing until we have subs
class RedisBus:
    """Redis Streams-backed event bus.

    Streams are durable: if a consumer restarts, it picks up from where it left
    off via the consumer group PEL. This is why Streams rather than Pub/Sub —
    messages sent while a consumer is offline are not lost.

    The Redis client MUST be created with decode_responses=True so all keys
    and values are returned as str. Use RedisBus.create(url) to get this right
    automatically.

    Payloads are stored as a single JSON blob under a 'data' field:
        XADD task.ws1.created * data '{"task_id": "...", "required_skills": {...}}'
    This handles nested dicts cleanly without per-field type coercion.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @classmethod
    async def create(cls, url: str) -> RedisBus:
        """Factory that creates a client with decode_responses=True."""
        client = Redis.from_url(url, decode_responses=True)
        return cls(client)

    async def _ensure_group(self, stream: str, group: str) -> None:
        """Create consumer group if it doesn't exist.

        BUSYGROUP is raised on every restart when the group already exists.
        This is expected and not an error — the try/except is mandatory.
        Uses '$' so a fresh group only sees new messages, not historical ones.
        """
        try:
            await self._redis.xgroup_create(stream, group, id="$", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, stream: str, payload: dict) -> None:
        """XADD payload as a JSON blob to a Redis Stream."""
        await self._redis.xadd(stream, {"data": json.dumps(payload)})

    async def subscribe(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        batch_size: int = 10,
        block_ms: int = 1000,
    ) -> AsyncIterator[tuple[str, dict]]:
        """Yield (message_id, payload) from a Redis Stream consumer group.

        Caller must call ack(stream, group, message_id) after processing each
        message. Without ack, crashed workers receive redelivery — which is the
        correct at-least-once behaviour, but processed messages pile up in the PEL.

        block_ms controls how long XREADGROUP waits for new messages before
        returning an empty result. The loop continues regardless so the generator
        never terminates on its own; cancel the task to stop consuming.
        """
        await self._ensure_group(stream, group)
        while True:
            results = await self._redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=batch_size,
                block=block_ms,
            )
            if not results:
                continue
            for _stream_name, messages in results:
                for msg_id, fields in messages:
                    payload = json.loads(fields["data"])
                    yield msg_id, payload

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        """XACK — remove a processed message from the Pending Entries List."""
        await self._redis.xack(stream, group, message_id)

    async def close(self) -> None:
        await self._redis.aclose()
