"""Integration tests for the in-process EventBus dispatch chain.

These tests wire real handlers into the real EventBus (no Redis) and verify
that the publish → handler → side-effect path works end-to-end. The goal is
to catch regressions in bus routing, handler exception isolation, and MRO-based
dispatch — none of which are testable by patching individual components.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from core.eventing.bus import EventBus, EventHandler
from core.eventing.bus.common import DomainEvent
from core.eventing.events.task_events import TaskUpdatedEvent
from worker.handlers.reflect_job import ReflectJobHandler
from worker.handlers.webhook import WebhookDeliveryHandler


# ── Minimal tracking handler ──────────────────────────────────────────────────

@dataclass
class _Tracking(EventHandler):
    """Captures every event it handles."""
    calls: list[DomainEvent] | None =None
    should_raise: bool = False

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    async def handle(self, event: DomainEvent) -> None:
        if self.should_raise:
            raise RuntimeError("handler exploded")
        self.calls.append(event)


def _bus() -> EventBus:
    loop = asyncio.get_event_loop()
    return EventBus(loop=loop)


# ── Dispatch basics ───────────────────────────────────────────────────────────

async def test_handler_receives_published_event(make_updated_event):
    bus = _bus()
    handler = _Tracking()
    bus.bind(TaskUpdatedEvent, handler)

    event = make_updated_event("open", "completed")
    await bus.apublish(event)
    await bus.drain_pending()

    assert len(handler.calls) == 1
    assert handler.calls[0] is event


async def test_multiple_handlers_all_called(make_updated_event):
    bus = _bus()
    h1, h2 = _Tracking(), _Tracking()
    bus.bind(TaskUpdatedEvent, h1)
    bus.bind(TaskUpdatedEvent, h2)

    event = make_updated_event("open", "completed")
    await bus.apublish(event)
    await bus.drain_pending()

    assert len(h1.calls) == 1
    assert len(h2.calls) == 1


async def test_exception_in_first_handler_does_not_block_second(make_updated_event):
    """Handler exceptions are isolated — fire-and-forget continues."""
    bus = _bus()
    bad_handler = _Tracking(should_raise=True)
    good_handler = _Tracking()
    bus.bind(TaskUpdatedEvent, bad_handler)
    bus.bind(TaskUpdatedEvent, good_handler)

    event = make_updated_event("open", "completed")
    await bus.apublish(event)
    await bus.drain_pending()

    assert len(good_handler.calls) == 1


async def test_unbound_event_type_not_dispatched(make_updated_event):
    bus = _bus()
    handler = _Tracking()
    bus.bind(TaskUpdatedEvent, handler)

    # Publish a DomainEvent subclass the handler is NOT bound to
    from core.eventing.events.task_events import TaskCreatedEvent
    from core.eventing.events.task_events import TaskSnapshot
    snapshot = make_updated_event("open", "open").state  # reuse snapshot factory
    event = TaskCreatedEvent(state=snapshot, workspace_id=uuid.uuid4())

    await bus.apublish(event)
    await bus.drain_pending()

    assert len(handler.calls) == 0


# ── Real handler integration ──────────────────────────────────────────────────

async def test_reflect_job_handler_enqueues_on_completed_self_execute(
    make_updated_event, arq_mock
):
    """ReflectJobHandler wired to EventBus enqueues a reflect job."""
    bus = _bus()
    bus.bind(TaskUpdatedEvent, ReflectJobHandler(arq_queue=arq_mock))

    agent_id = uuid.uuid4()
    exec_id = uuid.uuid4()
    event = make_updated_event(
        "executing", "completed",
        execution_path="self_execute",
        executing_agent_id=agent_id,
        execution_id=exec_id,
    )

    await bus.apublish(event)
    await bus.drain_pending()

    arq_mock.enqueue_job.assert_called_once()
    kwargs = arq_mock.enqueue_job.call_args.kwargs
    assert kwargs["status"] == "completed"
    assert kwargs["agent_id"] == str(agent_id)


async def test_reflect_job_handler_skips_decompose_path(make_updated_event, arq_mock):
    """Decompose tasks must not trigger reflect even when completed."""
    bus = _bus()
    bus.bind(TaskUpdatedEvent, ReflectJobHandler(arq_queue=arq_mock))

    event = make_updated_event(
        "executing", "completed",
        execution_path="decompose",
        executing_agent_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
    )

    await bus.apublish(event)
    await bus.drain_pending()

    arq_mock.enqueue_job.assert_not_called()


async def test_webhook_handler_enqueues_on_completed(make_updated_event, arq_mock):
    """WebhookDeliveryHandler wired to bus enqueues deliver_webhook."""
    bus = _bus()
    bus.bind(TaskUpdatedEvent, WebhookDeliveryHandler(arq_queue=arq_mock))

    exec_id = uuid.uuid4()
    event = make_updated_event(
        "executing", "completed",
        execution_id=exec_id,
    )

    await bus.apublish(event)
    await bus.drain_pending()

    arq_mock.enqueue_job.assert_called_once_with(
        "deliver_webhook",
        execution_id=str(exec_id),
        workspace_id=str(event.state.workspace_id),
    )


async def test_webhook_handler_skips_failed_task(make_updated_event, arq_mock):
    bus = _bus()
    bus.bind(TaskUpdatedEvent, WebhookDeliveryHandler(arq_queue=arq_mock))

    event = make_updated_event(
        "executing", "failed",
        execution_id=uuid.uuid4(),
    )

    await bus.apublish(event)
    await bus.drain_pending()

    arq_mock.enqueue_job.assert_not_called()


async def test_drain_pending_waits_for_all_handlers(make_updated_event):
    """drain_pending() must block until all fire-and-forget tasks complete."""
    results: list[bool] = []

    @dataclass
    class SlowHandler(EventHandler):
        async def handle(self, event: DomainEvent) -> None:
            await asyncio.sleep(0.01)
            results.append(True)

    bus = _bus()
    bus.bind(TaskUpdatedEvent, SlowHandler())

    event = make_updated_event("open", "completed")
    await bus.apublish(event)
    # Before drain: handler may not have finished
    await bus.drain_pending()
    # After drain: guaranteed complete
    assert results == [True]
