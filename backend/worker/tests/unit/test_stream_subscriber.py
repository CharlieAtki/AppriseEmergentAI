"""Tests for StreamSubscriber and _parse_stream_event.

The subscriber is the boundary between Redis Streams and the in-process bus.
Two failure modes matter most: an unknown event_type must be skipped without
crashing the loop, and any exception during parsing or dispatch must still
result in the message being acked — otherwise it sits in the Redis PEL forever
and gets redelivered indefinitely (the poison-message bug this file guards
against regressing).
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from core.eventing.events.stream_events import TaskCreatedStreamEvent
from worker.subscriber import (
    CFP_STREAM_REGISTRY,
    TASK_STREAM_REGISTRY,
    StreamSubscriber,
    _parse_stream_event,
)

# ── _parse_stream_event ────────────────────────────────────────────────────────


def _task_created_payload(**overrides) -> dict:
    payload = {
        "event_type": "task.created",
        "task_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "organisation_id": str(uuid.uuid4()),
        "required_skills": {"python": 1.0},
    }
    payload.update(overrides)
    return payload


def test_known_event_type_deserialises():
    event = _parse_stream_event(_task_created_payload(), TASK_STREAM_REGISTRY)
    assert isinstance(event, TaskCreatedStreamEvent)


def test_unknown_event_type_returns_none():
    payload = {"event_type": "some.future.event"}
    assert _parse_stream_event(payload, TASK_STREAM_REGISTRY) is None


def test_missing_event_type_key_returns_none():
    """No event_type at all — treated the same as unknown, not a crash."""
    assert _parse_stream_event({}, TASK_STREAM_REGISTRY) is None


def test_missing_required_field_raises():
    """Malformed payload (missing task_id) must raise — caller is responsible for
    catching it, logging, and still acking (see test_run_acks_on_parse_error)."""
    payload = _task_created_payload()
    del payload["task_id"]
    with pytest.raises(KeyError):
        _parse_stream_event(payload, TASK_STREAM_REGISTRY)


def test_registry_is_scoped_per_stream():
    """A cfp.issued payload is unknown to the task registry and vice versa."""
    assert _parse_stream_event({"event_type": "cfp.issued"}, TASK_STREAM_REGISTRY) is None
    assert _parse_stream_event({"event_type": "task.created"}, CFP_STREAM_REGISTRY) is None


# ── StreamSubscriber lifecycle ─────────────────────────────────────────────────


class _HangingBus:
    """Fake bus whose subscribe() never yields — used to test cancellation."""

    def __init__(self) -> None:
        self.ack = AsyncMock()

    async def subscribe(self, stream, group, consumer):
        await asyncio.Future()
        yield "unreachable", {}  # pragma: no cover


def _subscriber(bus, publish=None, registry=None) -> StreamSubscriber:
    return StreamSubscriber(
        bus=bus,
        publish=publish or AsyncMock(return_value=[]),
        stream="stream:task",
        group="worker-group",
        consumer="worker-test",
        registry=registry or TASK_STREAM_REGISTRY,
        name="task",
    )


async def test_start_spawns_named_task():
    sub = _subscriber(_HangingBus())
    await sub.start()
    try:
        assert sub._task is not None
        assert sub._task.get_name() == "task-subscriber"
        assert not sub._task.done()
    finally:
        await sub.stop()


async def test_stop_cancels_running_task():
    sub = _subscriber(_HangingBus())
    await sub.start()
    await sub.stop()
    assert sub._task.done()
    assert sub._task.cancelled()


async def test_stop_without_start_is_a_no_op():
    sub = _subscriber(_HangingBus())
    await sub.stop()  # must not raise


# ── _run() dispatch + ack-always behaviour ─────────────────────────────────────


class _ScriptedBus:
    """Fake bus that yields a fixed sequence of (msg_id, payload) then stops."""

    def __init__(self, messages: list[tuple[str, dict]]) -> None:
        self._messages = messages
        self.ack = AsyncMock()

    async def subscribe(self, stream, group, consumer):
        for msg_id, payload in self._messages:
            yield msg_id, payload


async def _run_to_completion(sub: StreamSubscriber) -> None:
    """Drive _run() directly — the fake bus's generator ends on its own,
    so the loop returns without needing start()/stop()."""
    await sub._run()


async def test_known_event_dispatches_and_acks():
    bus = _ScriptedBus([("1-0", _task_created_payload())])
    publish = AsyncMock(return_value=[])
    sub = _subscriber(bus, publish=publish)

    await _run_to_completion(sub)

    publish.assert_awaited_once()
    dispatched = publish.call_args.args[0]
    assert isinstance(dispatched, TaskCreatedStreamEvent)
    bus.ack.assert_awaited_once_with("stream:task", "worker-group", "1-0")


async def test_unknown_event_type_skips_publish_but_still_acks():
    bus = _ScriptedBus([("1-0", {"event_type": "some.future.event"})])
    publish = AsyncMock(return_value=[])
    sub = _subscriber(bus, publish=publish)

    await _run_to_completion(sub)

    publish.assert_not_called()
    bus.ack.assert_awaited_once_with("stream:task", "worker-group", "1-0")


async def test_malformed_payload_still_acks():
    """The poison-message regression test: a payload that fails to parse must
    not leave the message unacked in the PEL."""
    bad_payload = _task_created_payload()
    del bad_payload["task_id"]
    bus = _ScriptedBus([("1-0", bad_payload)])
    publish = AsyncMock(return_value=[])
    sub = _subscriber(bus, publish=publish)

    await _run_to_completion(sub)  # must not raise

    publish.assert_not_called()
    bus.ack.assert_awaited_once_with("stream:task", "worker-group", "1-0")


async def test_handler_exception_still_acks():
    """A handler task that raises must still result in an ack — gather()
    propagating is caught by _run()'s except, and ack fires in finally regardless."""

    async def _boom() -> None:
        raise RuntimeError("handler exploded")

    bus = _ScriptedBus([("1-0", _task_created_payload())])
    publish = AsyncMock(return_value=[asyncio.ensure_future(_boom())])
    sub = _subscriber(bus, publish=publish)

    await _run_to_completion(sub)  # must not raise

    bus.ack.assert_awaited_once_with("stream:task", "worker-group", "1-0")


async def test_multiple_messages_each_acked_independently():
    bus = _ScriptedBus(
        [
            ("1-0", _task_created_payload()),
            ("2-0", {"event_type": "unknown"}),
            ("3-0", _task_created_payload()),
        ]
    )
    publish = AsyncMock(return_value=[])
    sub = _subscriber(bus, publish=publish)

    await _run_to_completion(sub)

    assert bus.ack.await_count == 3
    acked_ids = [call.args[2] for call in bus.ack.await_args_list]
    assert acked_ids == ["1-0", "2-0", "3-0"]
