"""Tests for WebhookDeliveryHandler gate logic.

Webhook delivery fires only on "completed" + execution_id present.
A missed gate would silently skip webhook delivery; a wrong gate would fire
on failed tasks or fire before an execution row exists.
"""

from __future__ import annotations

import uuid

import pytest

from worker.handlers.webhook import WebhookDeliveryHandler


def _handler(arq_mock) -> WebhookDeliveryHandler:
    return WebhookDeliveryHandler(arq_queue=arq_mock)


# ── No-op cases ───────────────────────────────────────────────────────────────


async def test_no_status_change_skips(make_updated_event, arq_mock):
    event = make_updated_event(
        "completed",
        "completed",  # same → changed("status") = False
        execution_id=uuid.uuid4(),
    )
    await _handler(arq_mock).handle(event)
    arq_mock.enqueue_job.assert_not_called()


@pytest.mark.parametrize("status", ["failed", "expired", "executing", "open"])
async def test_non_completed_status_skips(make_updated_event, arq_mock, status):
    """Webhook only fires on "completed" — not on failure or any other terminal."""
    event = make_updated_event(
        "executing",
        status,
        execution_id=uuid.uuid4(),
    )
    await _handler(arq_mock).handle(event)
    arq_mock.enqueue_job.assert_not_called()


async def test_completed_without_execution_id_skips(make_updated_event, arq_mock):
    """execution_id guard prevents webhook before the execution row exists."""
    event = make_updated_event(
        "executing",
        "completed",
        execution_id=None,
    )
    await _handler(arq_mock).handle(event)
    arq_mock.enqueue_job.assert_not_called()


# ── Enqueue case ──────────────────────────────────────────────────────────────


async def test_completed_with_execution_id_enqueues(make_updated_event, arq_mock):
    exec_id = uuid.uuid4()
    event = make_updated_event(
        "executing",
        "completed",
        execution_id=exec_id,
    )
    ws_id = event.state.workspace_id

    await _handler(arq_mock).handle(event)

    arq_mock.enqueue_job.assert_called_once_with(
        "deliver_webhook",
        execution_id=str(exec_id),
        workspace_id=str(ws_id),
    )


async def test_enqueue_failure_does_not_raise(make_updated_event, arq_mock):
    """Lost enqueue is preferable to crashing other handlers — must not re-raise."""
    arq_mock.enqueue_job.side_effect = Exception("Redis unavailable")

    event = make_updated_event(
        "executing",
        "completed",
        execution_id=uuid.uuid4(),
    )
    # Must not raise
    await _handler(arq_mock).handle(event)
