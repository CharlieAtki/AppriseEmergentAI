"""Tests for deliver_webhook job — HMAC signing and retry schedule.

The HMAC signature is a security primitive; the retry delay table determines
when external systems receive retries. Both must be tested directly because
no end-to-end test can observe these without a live HTTP server.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from worker.jobs.deliver_webhook import _RETRY_DELAYS, _sign_body, deliver_webhook

# ── _sign_body (pure function) ────────────────────────────────────────────────


def test_sign_body_is_deterministic():
    body = b'{"event": "task.completed"}'
    secret = "s3cr3t"
    assert _sign_body(body, secret) == _sign_body(body, secret)


def test_sign_body_matches_hmac_sha256():
    body = b'{"event": "task.completed"}'
    secret = "mysecret"
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _sign_body(body, secret) == expected


def test_sign_body_different_body_different_digest():
    secret = "sec"
    assert _sign_body(b"body1", secret) != _sign_body(b"body2", secret)


def test_sign_body_different_secret_different_digest():
    body = b"body"
    assert _sign_body(body, "secret1") != _sign_body(body, "secret2")


def test_sign_body_returns_hex_string():
    result = _sign_body(b"data", "key")
    assert isinstance(result, str)
    # SHA-256 hex digest is always 64 characters
    assert len(result) == 64


# ── _RETRY_DELAYS schedule ────────────────────────────────────────────────────


def test_retry_delays_has_four_entries():
    """Exactly four attempts before giving up."""
    assert len(_RETRY_DELAYS) == 4


def test_retry_delays_values():
    """30s → 5m → 30m → 2h."""
    assert _RETRY_DELAYS == (30, 300, 1800, 7200)


def test_retry_delays_are_increasing():
    for i in range(len(_RETRY_DELAYS) - 1):
        assert _RETRY_DELAYS[i] < _RETRY_DELAYS[i + 1]


# ── deliver_webhook job: early exits ─────────────────────────────────────────


async def test_no_webhook_url_returns_early():
    """Workspace with no webhook URL → job returns without any HTTP call."""
    exec_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())

    execution = MagicMock()
    execution.organisation_id = uuid.uuid4()
    execution.task_id = None
    execution.completed_at = None
    execution.artifact = None

    workspace = MagicMock()
    workspace.result_webhook_url = None  # no URL configured
    workspace.webhook_secret = None

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[execution, workspace])

    @asynccontextmanager
    async def _gs():
        yield session

    wctx = MagicMock()
    wctx.arq_queue = AsyncMock()

    with (
        patch("worker.jobs.deliver_webhook.get_session", _gs),
        patch("worker.jobs.deliver_webhook.get_worker_context", return_value=wctx),
    ):
        await deliver_webhook({}, execution_id=exec_id, workspace_id=ws_id)

    # No session.add call (no delivery row created)
    session.add.assert_not_called()


async def test_missing_execution_returns_early():
    """If execution is not found, job returns without touching workspace."""
    exec_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())

    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _gs():
        yield session

    wctx = MagicMock()

    with (
        patch("worker.jobs.deliver_webhook.get_session", _gs),
        patch("worker.jobs.deliver_webhook.get_worker_context", return_value=wctx),
    ):
        await deliver_webhook({}, execution_id=exec_id, workspace_id=ws_id)

    wctx.arq_queue.enqueue_job.assert_not_called()


# ── deliver_webhook job: retry schedule ──────────────────────────────────────


async def _run_delivery_failure(attempt_count: int, mocker):
    """Run deliver_webhook with an HTTP failure at attempt_count, return (record, wctx)."""
    exec_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())
    delivery_id = f"dlv_{uuid.uuid4().hex}"

    execution = MagicMock()
    execution.organisation_id = uuid.uuid4()
    execution.task_id = None
    execution.completed_at = None
    execution.artifact = None

    workspace = MagicMock()
    workspace.result_webhook_url = "https://example.com/webhook"
    workspace.webhook_secret = "sec"

    record = MagicMock()
    record.attempt_count = attempt_count - 1  # will be incremented to attempt_count
    record.status = "pending"
    record.next_attempt_at = None

    load_session = AsyncMock()
    load_session.get = AsyncMock(side_effect=[execution, workspace])
    load_result = MagicMock()
    load_result.scalar_one_or_none.return_value = None  # existing delivery not terminal; proceed
    load_session.execute = AsyncMock(return_value=load_result)

    record_result = MagicMock()
    record_result.scalar_one_or_none.return_value = record
    record_session = AsyncMock()
    record_session.execute = AsyncMock(return_value=record_result)

    sessions = iter([load_session, record_session])

    @asynccontextmanager
    async def _gs():
        yield next(sessions)

    wctx = MagicMock()
    wctx.arq_queue = AsyncMock()
    wctx.arq_queue.enqueue_job = AsyncMock()

    # HTTP call fails
    with (
        patch("worker.jobs.deliver_webhook.get_session", _gs),
        patch("worker.jobs.deliver_webhook.get_worker_context", return_value=wctx),
        patch("worker.jobs.deliver_webhook.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_client_cls.return_value = mock_client

        await deliver_webhook({}, execution_id=exec_id, workspace_id=ws_id, delivery_id=delivery_id)

    return record, wctx


async def test_failure_attempt_1_schedules_retry_30s(mocker):
    record, wctx = await _run_delivery_failure(attempt_count=1, mocker=mocker)
    wctx.arq_queue.enqueue_job.assert_called_once()
    call_kwargs = wctx.arq_queue.enqueue_job.call_args.kwargs
    from datetime import timedelta

    assert call_kwargs["_defer_by"] == timedelta(seconds=30)
    assert record.status != "failed"


async def test_failure_attempt_3_schedules_retry_1800s(mocker):
    _record, wctx = await _run_delivery_failure(attempt_count=3, mocker=mocker)
    wctx.arq_queue.enqueue_job.assert_called_once()
    call_kwargs = wctx.arq_queue.enqueue_job.call_args.kwargs
    from datetime import timedelta

    assert call_kwargs["_defer_by"] == timedelta(seconds=1800)


async def test_failure_attempt_5_marks_failed_no_retry(mocker):
    """After all 4 retry slots exhausted (5th attempt), delivery is marked 'failed'.

    _RETRY_DELAYS has 4 entries (indices 0-3). At attempt_count=5, idx=4,
    which is out of range → status='failed', no further enqueue.
    """
    record, wctx = await _run_delivery_failure(attempt_count=5, mocker=mocker)
    wctx.arq_queue.enqueue_job.assert_not_called()
    assert record.status == "failed"
