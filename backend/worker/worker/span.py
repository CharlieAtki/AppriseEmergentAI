from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from core.database import get_session
from worker.context import get_worker_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


_current_span: ContextVar[JobSpan] = ContextVar("current_span")


def current_span() -> JobSpan:
    """Access the active JobSpan from anywhere in the job call stack via ContextVar."""
    try:
        return _current_span.get()
    except LookupError:
        raise RuntimeError("No active JobSpan — called outside a job context?")


class JobSpan:
    """Job-level async context manager.

    Sets itself on a ContextVar on enter so nothing needs to be passed through
    function arguments. Tools in core/agents/tools/ can call current_span().emit()
    directly from within LangGraph nodes.

    Captures ARQ job metadata (job_id, job_try) for distributed tracing and
    idempotency guards in future phases.

    Does NOT create or finalise the TaskExecution row — that is the job's responsibility.
    """

    def __init__(
        self,
        agent_id: uuid.UUID,
        task_id: uuid.UUID,
        workspace_id: uuid.UUID,
        *,
        job_id: str | None = None,
        job_try: int = 1,
    ) -> None:
        self._wctx        = get_worker_context()
        self.agent_id     = agent_id
        self.task_id      = task_id
        self.workspace_id = workspace_id
        self.job_id       = job_id    # ARQ-assigned job ID — stable across retries
        self.job_try      = job_try   # retry attempt number — 1 on first run
        self._events: list[dict] = []
        self._token: Token | None = None

    async def __aenter__(self) -> JobSpan:
        self._token = _current_span.set(self)
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
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

    async def emit(self, event_type: str, data: dict | None = None) -> None:
        """Publish a structured event immediately to Redis Pub/Sub.

        The API WebSocket endpoint subscribes to workspace:{id}:events and forwards
        events to connected browsers in real time. Events also accumulate in self._events
        for storage in TaskExecution.tool_trace after the job completes.
        """
        event: dict = {
            "type":         event_type,
            "agent_id":     str(self.agent_id),
            "task_id":      str(self.task_id),
            "workspace_id": str(self.workspace_id),
            "job_id":       self.job_id,
            "job_try":      self.job_try,
            "ts":           datetime.now(timezone.utc).isoformat(),
            **(data or {}),
        }
        self._events.append(event)
        await self._wctx.redis.publish(
            f"workspace:{self.workspace_id}:events",
            json.dumps(event),
        )

    @property
    def events(self) -> list[dict]:
        """Accumulated events — written to TaskExecution.tool_trace on completion."""
        return list(self._events)
