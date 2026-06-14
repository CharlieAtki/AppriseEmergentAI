from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from core.database import get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ArqJobMeta:
    """Typed view of the ARQ job context dict parsed once at the job boundary.

    ARQ passes a raw ``dict`` as the first argument to every job function.
    ``from_ctx`` extracts the known fields so no other code ever spelunks the
    dict directly — the rest of the call stack works with typed values.
    """

    job_id:  str | None  # ARQ-assigned ID, stable across retries
    job_try: int          # 1 on first attempt, increments on each ARQ retry

    @classmethod
    def from_ctx(cls, ctx: dict[str, Any]) -> ArqJobMeta:
        return cls(
            job_id=ctx.get("job_id"),
            job_try=ctx.get("job_try", 1),
        )


class NoActiveSpanError(RuntimeError):
    """Raised when current_span() is called outside an active JobSpan context."""


_current_span: ContextVar[JobSpan] = ContextVar("current_span")


def current_span() -> JobSpan:
    """Access the active JobSpan from anywhere in the job call stack via ContextVar."""
    try:
        return _current_span.get()
    except LookupError as err:
        raise NoActiveSpanError("No active JobSpan — called outside a job context") from err


class JobSpan:
    """Job-level async context manager.

    Sets itself on a ContextVar on enter so nothing needs to be passed through
    function arguments. Tools in core/agents/tools/ can call current_span().emit()
    directly from within LangGraph nodes.

    Does NOT create or finalise the TaskExecution row — that is the job's responsibility.

    ``redis_publish`` is the narrow callable used by ``emit()`` to push events to
    Redis Pub/Sub. Pass ``wctx.redis.publish`` at the call site — injected rather
    than resolved via ``get_worker_context()`` so the span has no hidden global
    dependency and can be constructed in tests with a mock callable.

    ``meta`` carries the ARQ job identity parsed from ``ctx`` at the job boundary
    via ``ArqJobMeta.from_ctx(ctx)``. Its fields appear in every emitted event for
    distributed tracing and retry correlation.
    """

    def __init__(
        self,
        agent_id: uuid.UUID,
        task_id: uuid.UUID,
        workspace_id: uuid.UUID,
        *,
        redis_publish: Callable[[str, str], Awaitable[None]],
        meta: ArqJobMeta,
    ) -> None:
        self._publish     = redis_publish
        self.meta         = meta
        self.agent_id     = agent_id
        self.task_id      = task_id
        self.workspace_id = workspace_id
        self._events: list[dict[str, object]] = []
        self._token: Token[JobSpan] | None = None

    async def __aenter__(self) -> JobSpan:
        self._token = _current_span.set(self)
        return self

    async def __aexit__(self, _exc_type: object, _exc_val: object, _exc_tb: object) -> None:
        if self._token is not None:
            _current_span.reset(self._token)
        # Never suppress exceptions — let them propagate to ARQ for retry logic.

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Open a DB session for one phase (read or write).

        Auto-commits on clean exit, rolls back on exception — from core.database.get_session().
        Call once per phase. Never hold a session open during graph execution.
        """
        async with get_session() as s:
            yield s

    async def emit(self, event_type: str, data: dict[str, object] | None = None) -> None:
        """Publish a structured event immediately to Redis Pub/Sub.

        The API WebSocket endpoint subscribes to workspace:{id}:events and forwards
        events to connected browsers in real time. Events also accumulate in self._events
        for storage in TaskExecution.tool_trace after the job completes.

        ``default=str`` in json.dumps guards against non-serialisable values that
        callers may pass in ``data`` (e.g. UUID, datetime, Decimal).
        """
        reserved = {"type", "agent_id", "task_id", "workspace_id", "job_id", "job_try", "ts"}
        extra: dict[str, object] = {}
        if data:
            collision = reserved.intersection(data)
            if collision:
                raise ValueError(f"emit() payload contains reserved keys: {sorted(collision)}")
            extra = dict(data)

        event: dict[str, object] = {
            "type":         event_type,
            "agent_id":     str(self.agent_id),
            "task_id":      str(self.task_id),
            "workspace_id": str(self.workspace_id),
            "job_id":       self.meta.job_id,
            "job_try":      self.meta.job_try,
            "ts":           datetime.now(timezone.utc).isoformat(),
            **extra,
        }
        self._events.append(event)
        await self._publish(
            f"workspace:{self.workspace_id}:events",
            json.dumps(event, default=str),
        )

    @property
    def events(self) -> list[dict[str, object]]:
        """Accumulated events — written to TaskExecution.tool_trace on completion."""
        return list(self._events)
