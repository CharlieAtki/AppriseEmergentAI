"""Tests for ArqJobMeta and JobSpan.

These are the two lowest-level worker primitives. ArqJobMeta is the only code
that reads the ARQ ctx dict; a bug here silently breaks retry correlation across
all jobs. JobSpan's ContextVar is the mechanism every stage uses to emit events
without thread-unsafe parameter passing.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest
from worker.span import ArqJobMeta, JobSpan, NoActiveSpanError, current_span

# ── ArqJobMeta.from_ctx ───────────────────────────────────────────────────────


def test_from_ctx_reads_job_id_and_try():
    ctx = {"job_id": "arq:job:abc123", "job_try": 3}
    meta = ArqJobMeta.from_ctx(ctx)
    assert meta.job_id == "arq:job:abc123"
    assert meta.job_try == 3


def test_from_ctx_empty_dict_uses_defaults():
    meta = ArqJobMeta.from_ctx({})
    assert meta.job_id is None
    assert meta.job_try == 1


def test_from_ctx_missing_job_try_defaults_to_one():
    meta = ArqJobMeta.from_ctx({"job_id": "x"})
    assert meta.job_try == 1


def test_from_ctx_extra_keys_ignored():
    """ARQ may add fields in future versions — extra keys must not raise."""
    meta = ArqJobMeta.from_ctx({"job_id": "x", "job_try": 2, "future_field": "ignored"})
    assert meta.job_id == "x"


# ── JobSpan.emit ──────────────────────────────────────────────────────────────


def _make_span(agent_id=None, task_id=None, workspace_id=None):
    redis_publish = AsyncMock()
    meta = ArqJobMeta(job_id="test-job", job_try=1)
    span = JobSpan(
        agent_id=agent_id or uuid.uuid4(),
        task_id=task_id or uuid.uuid4(),
        workspace_id=workspace_id or uuid.uuid4(),
        redis_publish=redis_publish,
        meta=meta,
    )
    return span, redis_publish


async def test_emit_calls_publish_on_correct_channel():
    ws_id = uuid.uuid4()
    span, publish = _make_span(workspace_id=ws_id)

    async with span:
        await span.emit("test_event", {"key": "val"})

    publish.assert_called_once()
    channel = publish.call_args.args[0]
    assert channel == f"workspace:{ws_id}:events"


async def test_emit_json_payload_contains_event_type():
    span, publish = _make_span()

    async with span:
        await span.emit("task.started", {"step": 1})

    payload_str = publish.call_args.args[1]
    payload = json.loads(payload_str)
    assert payload["type"] == "task.started"
    assert payload["step"] == 1


async def test_emit_accumulates_in_events():
    span, _ = _make_span()

    async with span:
        await span.emit("event_a", {})
        await span.emit("event_b", {"x": 1})

    events = span.events
    assert len(events) == 2
    assert events[0]["type"] == "event_a"
    assert events[1]["type"] == "event_b"


async def test_emit_no_data_publishes_without_error():
    span, publish = _make_span()
    async with span:
        await span.emit("bare_event")
    publish.assert_called_once()


async def test_events_property_returns_copy():
    """Mutating the returned list must not affect the internal accumulator."""
    span, _ = _make_span()
    async with span:
        await span.emit("e1", {})
        span.events.clear()  # mutate the copy
        await span.emit("e2", {})

    assert len(span.events) == 2  # internal list untouched


async def test_emit_includes_job_meta_fields():
    """job_id and job_try are included in every emitted event for tracing."""
    span, publish = _make_span()
    span.meta = ArqJobMeta(job_id="trace-id-999", job_try=2)

    async with span:
        await span.emit("checked")

    payload = json.loads(publish.call_args.args[1])
    assert payload["job_id"] == "trace-id-999"
    assert payload["job_try"] == 2


# ── ContextVar behaviour ──────────────────────────────────────────────────────


async def test_current_span_outside_context_raises():
    with pytest.raises(NoActiveSpanError):
        current_span()


async def test_current_span_inside_context_returns_span():
    span, _ = _make_span()
    async with span:
        assert current_span() is span


async def test_current_span_after_exit_raises():
    span, _ = _make_span()
    async with span:
        pass
    # Token reset by __aexit__ — ContextVar reverts to unset
    with pytest.raises(NoActiveSpanError):
        current_span()


async def test_nested_spans_restore_outer():
    """Inner span shadows outer; after inner exits, outer is accessible again."""
    outer, _ = _make_span()
    inner, _ = _make_span()

    async with outer:
        assert current_span() is outer
        async with inner:
            assert current_span() is inner
        assert current_span() is outer
