from __future__ import annotations

import asyncio
import logging
import uuid

from core.eventing.activity.workspace_stream_logger import channel_for
from core.utils.retry import is_retryable_redis, retry_async
from fastapi import WebSocket
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Pause between exhausted retry_async cycles before starting a fresh one — keeps
# _listen alive indefinitely across a prolonged Redis outage instead of giving up
# after retry_async's bounded attempts, without hand-rolling a second backoff scheme.
_RECONNECT_PAUSE_SECONDS = 5


class WorkspaceConnectionRegistry:
    """One instance per API process, held on app.state.

    Multiplexes N WebSocket clients onto a single Redis Pub/Sub connection per
    workspace — a route that opened redis.pubsub() per browser connection would tie
    up one dedicated Redis connection per viewer indefinitely, a real connection-count
    cliff (maxclients) at a few hundred concurrent viewers. Subscribes on the first
    viewer for a workspace, unsubscribes when the last one disconnects.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._sockets: dict[uuid.UUID, set[WebSocket]] = {}
        self._listeners: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, workspace_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._sockets.setdefault(workspace_id, set())
            first = not sockets
            sockets.add(websocket)
            if first:
                self._listeners[workspace_id] = asyncio.create_task(self._listen(workspace_id))

    async def unsubscribe(self, workspace_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._sockets.get(workspace_id)
            if sockets is None:
                return
            sockets.discard(websocket)
            if not sockets:
                del self._sockets[workspace_id]
                self._listeners.pop(workspace_id).cancel()

    async def _listen(self, workspace_id: uuid.UUID) -> None:
        """Runs while >=1 viewer is connected, cancelled by unsubscribe() on last
        disconnect. Reconnects on a transient Redis drop via retry_async
        (core.utils.retry) instead of dying permanently on first failure — a
        dropped Redis connection must not silently strand every viewer of this
        workspace with no live updates until they happen to reload the page.
        """
        while workspace_id in self._sockets:
            try:
                await retry_async(
                    lambda: self._drain_once(workspace_id),
                    is_retryable=is_retryable_redis,
                    max_attempts=5,
                    backoff=1.0,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "WorkspaceConnectionRegistry: exhausted reconnect attempts for "
                    "workspace=%s — pausing %ds before trying again",
                    workspace_id,
                    _RECONNECT_PAUSE_SECONDS,
                )
                await asyncio.sleep(_RECONNECT_PAUSE_SECONDS)

    async def _drain_once(self, workspace_id: uuid.UUID) -> None:
        """One subscribe-and-consume cycle — raises on a dropped Redis connection
        so retry_async can reconnect; returns normally only when the last local
        viewer disconnects (fan-out failure path below)."""
        pubsub = self._redis.pubsub()
        channel = channel_for(workspace_id)
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                for ws in list(self._sockets.get(workspace_id, ())):
                    try:
                        await ws.send_text(message["data"])
                    except Exception:
                        async with self._lock:
                            sockets = self._sockets.get(workspace_id)
                            if sockets is None:
                                continue
                            sockets.discard(ws)
                            if not sockets:
                                del self._sockets[workspace_id]
                                self._listeners.pop(workspace_id, None)
                                return  # last viewer gone — end this listener, `finally` cleans up pubsub
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
