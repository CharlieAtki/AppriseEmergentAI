"""Tests for WorkspaceConnectionRegistry — the per-API-process Redis Pub/Sub
multiplexer for GET /workspaces/{id}/stream.

The concurrency path here is the highest-risk part of this feature: a listener
task is spawned on the first viewer and cancelled on the last disconnect. These
tests confirm the cancellation actually runs the cleanup (pubsub.unsubscribe +
aclose) rather than just requesting cancellation and leaving a dangling
subscription — the exact failure mode APP-6's own spec calls out.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.ws.registry import WorkspaceConnectionRegistry
from redis.exceptions import ConnectionError as RedisConnectionError


class _FakePubSub:
    """Minimal stand-in for redis.asyncio.client.PubSub.

    listen() blocks on an internal queue forever, mirroring real Pub/Sub's
    behaviour of never terminating on its own — the only way _listen() exits
    is via task cancellation, same as production.
    """

    def __init__(self) -> None:
        self.subscribe = AsyncMock()
        self.unsubscribe = AsyncMock()
        self.aclose = AsyncMock()
        self._queue: asyncio.Queue = asyncio.Queue()

    async def listen(self):
        while True:
            message = await self._queue.get()
            yield message

    async def push(self, message: dict) -> None:
        await self._queue.put(message)


def _make_redis(pubsub: _FakePubSub) -> MagicMock:
    redis = MagicMock()
    redis.pubsub = MagicMock(return_value=pubsub)
    return redis


def _make_ws() -> AsyncMock:
    return AsyncMock()


async def test_subscribe_first_viewer_opens_one_pubsub_subscription():
    pubsub = _FakePubSub()
    redis = _make_redis(pubsub)
    registry = WorkspaceConnectionRegistry(redis)
    ws_id = uuid.uuid4()
    ws = _make_ws()

    await registry.subscribe(ws_id, ws)
    await asyncio.sleep(0)  # let the spawned listener task reach pubsub.subscribe

    redis.pubsub.assert_called_once()
    pubsub.subscribe.assert_awaited_once_with(f"workspace:{ws_id}:events")

    await registry.unsubscribe(ws_id, ws)


async def test_second_viewer_reuses_the_same_pubsub_connection():
    """N viewers on one workspace must cost one Redis connection, not N."""
    pubsub = _FakePubSub()
    redis = _make_redis(pubsub)
    registry = WorkspaceConnectionRegistry(redis)
    ws_id = uuid.uuid4()
    ws1, ws2 = _make_ws(), _make_ws()

    await registry.subscribe(ws_id, ws1)
    await asyncio.sleep(0)
    await registry.subscribe(ws_id, ws2)
    await asyncio.sleep(0)

    redis.pubsub.assert_called_once()
    pubsub.subscribe.assert_awaited_once()

    await registry.unsubscribe(ws_id, ws1)
    await registry.unsubscribe(ws_id, ws2)


async def test_message_is_fanned_out_to_every_local_socket():
    pubsub = _FakePubSub()
    redis = _make_redis(pubsub)
    registry = WorkspaceConnectionRegistry(redis)
    ws_id = uuid.uuid4()
    ws1, ws2 = _make_ws(), _make_ws()

    await registry.subscribe(ws_id, ws1)
    await registry.subscribe(ws_id, ws2)
    await asyncio.sleep(0)

    await pubsub.push({"type": "message", "data": '{"type":"task.completed"}'})
    await asyncio.sleep(0)

    ws1.send_text.assert_awaited_once_with('{"type":"task.completed"}')
    ws2.send_text.assert_awaited_once_with('{"type":"task.completed"}')

    await registry.unsubscribe(ws_id, ws1)
    await registry.unsubscribe(ws_id, ws2)


async def test_non_message_pubsub_events_are_ignored():
    """Redis emits type='subscribe'/'unsubscribe' confirmations too — only
    type='message' carries an actual dashboard event."""
    pubsub = _FakePubSub()
    redis = _make_redis(pubsub)
    registry = WorkspaceConnectionRegistry(redis)
    ws_id = uuid.uuid4()
    ws = _make_ws()

    await registry.subscribe(ws_id, ws)
    await asyncio.sleep(0)

    await pubsub.push({"type": "subscribe", "data": 1})
    await asyncio.sleep(0)

    ws.send_text.assert_not_called()

    await registry.unsubscribe(ws_id, ws)


async def test_failed_send_removes_only_the_dead_socket():
    pubsub = _FakePubSub()
    redis = _make_redis(pubsub)
    registry = WorkspaceConnectionRegistry(redis)
    ws_id = uuid.uuid4()
    dead_ws = _make_ws()
    dead_ws.send_text.side_effect = RuntimeError("connection closed")
    alive_ws = _make_ws()

    await registry.subscribe(ws_id, dead_ws)
    await registry.subscribe(ws_id, alive_ws)
    await asyncio.sleep(0)

    await pubsub.push({"type": "message", "data": "payload"})
    await asyncio.sleep(0)

    alive_ws.send_text.assert_awaited_once_with("payload")
    assert dead_ws not in registry._sockets[ws_id]
    assert alive_ws in registry._sockets[ws_id]

    await registry.unsubscribe(ws_id, alive_ws)


async def test_last_disconnect_cancels_listener_and_runs_cleanup():
    """The riskiest path: does cancelling the listener task actually run its
    finally block (unsubscribe + aclose), or does cancellation just orphan it?
    """
    pubsub = _FakePubSub()
    redis = _make_redis(pubsub)
    registry = WorkspaceConnectionRegistry(redis)
    ws_id = uuid.uuid4()
    ws = _make_ws()

    await registry.subscribe(ws_id, ws)
    await asyncio.sleep(0)  # listener task now blocked inside pubsub.listen()

    listener_task = registry._listeners[ws_id]
    await registry.unsubscribe(ws_id, ws)

    with pytest.raises(asyncio.CancelledError):
        await listener_task

    pubsub.unsubscribe.assert_awaited_once_with(f"workspace:{ws_id}:events")
    pubsub.aclose.assert_awaited_once()
    assert ws_id not in registry._sockets
    assert ws_id not in registry._listeners


class _FlakyPubSub:
    """subscribe() succeeds; the first listen() raises a transient Redis error,
    the second (post-reconnect) behaves like a normal long-lived subscription."""

    def __init__(self) -> None:
        self.subscribe = AsyncMock()
        self.unsubscribe = AsyncMock()
        self.aclose = AsyncMock()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._listen_calls = 0

    async def listen(self):
        self._listen_calls += 1
        if self._listen_calls == 1:
            raise RedisConnectionError("connection reset")
        while True:
            message = await self._queue.get()
            yield message

    async def push(self, message: dict) -> None:
        await self._queue.put(message)


async def test_listen_reconnects_after_transient_redis_error():
    """A dropped Redis connection must not kill the listener permanently — every
    viewer of this workspace would be silently stranded with no live updates
    until they happened to reload. retry_async (core.utils.retry) should
    reconnect (fresh subscribe) rather than letting _listen die on first failure.
    """
    pubsub = _FlakyPubSub()
    redis = _make_redis(pubsub)
    registry = WorkspaceConnectionRegistry(redis)
    ws_id = uuid.uuid4()
    ws = _make_ws()

    # core.utils.retry does `import asyncio` — that name is the *same* asyncio
    # module object everywhere in the process, so patching .sleep on it globally
    # would also swallow this test's own `await asyncio.sleep(0)` yields (they'd
    # stop actually yielding to the scheduler, and the listener task would never
    # get to run until event-loop shutdown). The side_effect below still performs
    # a real, zero-delay sleep — it speeds up retry_async's backoff without
    # breaking cooperative scheduling for the rest of this test.
    real_sleep = asyncio.sleep

    async def instant_sleep(_delay: float, *args: object, **kwargs: object) -> None:
        await real_sleep(0)

    with patch("core.utils.retry.asyncio.sleep", AsyncMock(side_effect=instant_sleep)):
        await registry.subscribe(ws_id, ws)
        # Let the listener hit the failing listen() call, retry_async back off
        # (sped up above), and reconnect.
        for _ in range(5):
            await real_sleep(0)

        assert pubsub.subscribe.await_count >= 2  # reconnected: subscribed again

        await pubsub.push({"type": "message", "data": "still alive"})
        await real_sleep(0)
        ws.send_text.assert_awaited_once_with("still alive")

        await registry.unsubscribe(ws_id, ws)


async def test_unsubscribe_unknown_workspace_is_a_noop():
    pubsub = _FakePubSub()
    redis = _make_redis(pubsub)
    registry = WorkspaceConnectionRegistry(redis)

    await registry.unsubscribe(uuid.uuid4(), _make_ws())  # must not raise
