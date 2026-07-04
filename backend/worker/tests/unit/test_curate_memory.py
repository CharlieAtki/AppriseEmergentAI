"""Tests for worker.jobs.curate_memory — structured_call hardening.

Before this, a single malformed LLM response aborted the entire cron run for every
remaining agent in the loop. structured_call.run()'s retry-then-fallback means a
transient glitch is absorbed, and only a persistent failure degrades to "nothing
flagged this round" for that one agent — the loop still continues.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from core.memory.types import MemoryItem
from worker.jobs.curate_memory import curate_memory


def _make_agent(agent_id=None, workspace_id=None) -> MagicMock:
    a = MagicMock()
    a.id = agent_id or uuid.uuid4()
    a.workspace_id = workspace_id or uuid.uuid4()
    return a


def _make_item(item_id: str) -> MemoryItem:
    return MemoryItem(
        tier="procedural",
        id=item_id,
        score=1.0,
        text="always use context managers",
        payload={"domain": "python", "last_accessed_at": "2026-01-01"},
    )


def _patch_session(agents: list[MagicMock]):
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = agents

    async def _execute(*args, **kwargs):
        return result

    session.execute = AsyncMock(side_effect=_execute)

    @asynccontextmanager
    async def _gs():
        yield session

    return _gs


async def test_persistent_parse_failure_does_not_abort_remaining_agents():
    agent_a, agent_b = _make_agent(), _make_agent()

    wctx = MagicMock()
    wctx.memory.scroll_all_procedures = AsyncMock(
        side_effect=[[_make_item("rule-a")], [_make_item("rule-b")]]
    )
    wctx.memory.archive_procedures = AsyncMock()
    # Agent A's LLM response never parses; agent B's does.
    wctx.llm_router.complete = AsyncMock(
        side_effect=[
            "not json",
            "not json",
            '{"flagged": [{"id": "rule-b", "verdict": "stale", "reason": "old"}]}',
        ]
    )

    with (
        patch("worker.jobs.curate_memory.get_session", _patch_session([agent_a, agent_b])),
        patch("worker.jobs.curate_memory.get_worker_context", return_value=wctx),
    ):
        await curate_memory({})

    # Agent A: both attempts failed to parse -> fallback (flagged=[]) -> nothing archived for A.
    # Agent B: parses fine -> archived. The loop was not aborted by A's failure.
    wctx.memory.archive_procedures.assert_called_once_with(["rule-b"])


async def test_transient_parse_failure_recovers_via_retry():
    agent = _make_agent()

    wctx = MagicMock()
    wctx.memory.scroll_all_procedures = AsyncMock(return_value=[_make_item("rule-a")])
    wctx.memory.archive_procedures = AsyncMock()
    wctx.llm_router.complete = AsyncMock(
        side_effect=[
            "not json",
            '{"flagged": [{"id": "rule-a", "verdict": "stale", "reason": "old"}]}',
        ]
    )

    with (
        patch("worker.jobs.curate_memory.get_session", _patch_session([agent])),
        patch("worker.jobs.curate_memory.get_worker_context", return_value=wctx),
    ):
        await curate_memory({})

    wctx.memory.archive_procedures.assert_called_once_with(["rule-a"])
    assert wctx.llm_router.complete.call_count == 2


async def test_non_parse_exception_does_not_abort_remaining_agents():
    """structured_call.run() only catches ValidationError — retry_async re-raises any
    other exception immediately since is_retryable only matches ValidationError. A
    non-parse failure (network error, vendor SDK exception, etc.) from
    llm_router.complete is therefore caught by curate_memory's per-agent try/except,
    logged, and skipped — the loop still processes the remaining agents.
    """
    agent_a, agent_b = _make_agent(), _make_agent()

    wctx = MagicMock()
    wctx.memory.scroll_all_procedures = AsyncMock(
        side_effect=[[_make_item("rule-a")], [_make_item("rule-b")]]
    )
    wctx.memory.archive_procedures = AsyncMock()
    # Agent A's call raises outright; agent B's call parses fine.
    wctx.llm_router.complete = AsyncMock(
        side_effect=[
            RuntimeError("vendor call failed"),
            '{"flagged": [{"id": "rule-b", "verdict": "stale", "reason": "old"}]}',
        ]
    )

    with (
        patch("worker.jobs.curate_memory.get_session", _patch_session([agent_a, agent_b])),
        patch("worker.jobs.curate_memory.get_worker_context", return_value=wctx),
    ):
        await curate_memory({})

    # Agent A's exception was caught and skipped; agent B was still processed and archived.
    wctx.memory.archive_procedures.assert_called_once_with(["rule-b"])
