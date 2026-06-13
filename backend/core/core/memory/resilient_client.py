from __future__ import annotations

import asyncio

from qdrant_client import AsyncQdrantClient

from core.utils.retry import is_retryable_http, retry_async


class ResilientQdrantClient:
    """Wraps AsyncQdrantClient to retry transient failures on every async call.

    Injected at worker startup so AgentMemory is unaware of retry mechanics.
    Non-async attributes pass through unchanged.
    """

    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    def __getattr__(self, name: str):
        attr = getattr(self._client, name)
        if asyncio.iscoroutinefunction(attr):
            async def _retrying(*args, **kwargs):
                return await retry_async(
                    lambda: attr(*args, **kwargs),
                    is_retryable=is_retryable_http,
                )
            return _retrying
        return attr