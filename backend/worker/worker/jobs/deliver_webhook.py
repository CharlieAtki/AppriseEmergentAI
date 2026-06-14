from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from core.database import get_session
from core.models.tasks import Task, TaskExecution, WebhookDelivery
from core.models.tenant import Workspace
from worker.context import get_worker_context

logger = logging.getLogger(__name__)

_RETRY_DELAYS: tuple[int, ...] = (30, 300, 1800, 7200)  # 30s, 5m, 30m, 2h


# Pydantic is used here for outgoing HTTP serialisation, not request validation.
# model_dump_json() handles UUID → string and datetime → ISO 8601 automatically,
# which is the contract external webhook consumers depend on. The worker makes
# HTTP calls — it does not serve them — so this is not a violation of the
# "worker/ never serves HTTP" rule.


class _WebhookArtefact(BaseModel):
    """The task output embedded in the webhook body sent to external consumers."""

    model_config = ConfigDict(frozen=True)

    type: Literal["text"] = "text"
    content: str | None


class _WebhookPayload(BaseModel):
    """Outgoing webhook contract posted to ``workspace.result_webhook_url``.

    Frozen because the payload is constructed once, serialised, and never mutated.
    Field names are the external API surface customers integrate against — do not
    rename without a versioning strategy.
    """

    model_config = ConfigDict(frozen=True)

    delivery_id: str
    event: Literal["task.completed"] = "task.completed"
    task_id: uuid.UUID | None
    workspace_id: uuid.UUID
    completed_at: datetime | None
    external_ref: str | None
    artefact: _WebhookArtefact


def _sign_body(body: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 hex digest used in the ``X-Apprise-Signature`` header.

    Pure function — no I/O. Consumers verify this signature to confirm the payload
    originated from Apprise and was not tampered with in transit.
    """
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def deliver_webhook(
    ctx: dict[str, Any],
    execution_id: str,
    workspace_id: str,
    delivery_id: str | None = None,
) -> None:
    """ARQ job: POST a ``task.completed`` webhook to ``workspace.result_webhook_url``.

    Three phases, each with its own session so no connection is held during I/O:

    1. Load — fetch ``TaskExecution``, ``Workspace``, and optionally ``Task`` from
       Postgres. Capture all scalar values before the session closes (ORM objects
       must not be accessed after the session that loaded them closes). Create the
       ``WebhookDelivery`` audit row on the first attempt (``delivery_id`` is None).

    2. Deliver — build the signed ``_WebhookPayload`` body and POST it via httpx.
       Exceptions are caught and recorded as ``last_error``; they do not re-raise
       because retry is self-managed (step 3) rather than delegated to ARQ's
       default retry mechanism. Self-managed retry gives controlled exponential
       backoff instead of ARQ's fixed delay.

    3. Record — update the ``WebhookDelivery`` row with the outcome. On failure,
       enqueue a new ``deliver_webhook`` job deferred by ``_RETRY_DELAYS[attempt]``
       (30 s → 5 m → 30 m → 2 h). After four attempts the delivery is marked
       ``"failed"`` and no further retries are scheduled.

    ``webhook_secret`` is stored as plaintext — intentional. HMAC signing requires
    the raw secret; it cannot be hashed like a password. Treat it as a private key:
    never include it in API responses, never log it, never SELECT it outside this job.
    """
    wctx = get_worker_context()
    exec_uuid = uuid.UUID(execution_id)
    ws_uuid = uuid.UUID(workspace_id)

    async with get_session() as session:
        execution = await session.get(TaskExecution, exec_uuid)
        workspace = await session.get(Workspace, ws_uuid)

        if execution is None or workspace is None:
            logger.warning(
                "deliver_webhook: execution or workspace not found exec=%s ws=%s",
                execution_id,
                workspace_id,
            )
            return

        if not workspace.result_webhook_url:
            return

        target_url: str = workspace.result_webhook_url
        webhook_secret: str | None = workspace.webhook_secret
        org_id = execution.organisation_id
        task_id = execution.task_id
        completed_at = execution.completed_at
        artifact = execution.artifact

        external_ref = None
        if task_id:
            task = await session.get(Task, task_id)
            if task:
                external_ref = task.external_ref

        if delivery_id is not None:
            existing = (
                await session.execute(
                    select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
                )
            ).scalar_one_or_none()
            if existing is not None and existing.status in ("sent", "failed"):
                logger.info(
                    "deliver_webhook: delivery=%s already terminal (status=%s), skipping",
                    delivery_id,
                    existing.status,
                )
                return

        if delivery_id is None:
            delivery_id = f"dlv_{uuid.uuid4().hex}"
            delivery = WebhookDelivery(
                delivery_id=delivery_id,
                organisation_id=org_id,
                workspace_id=ws_uuid,
                task_execution_id=exec_uuid,
                target_url=target_url,
                status="pending",
            )
            session.add(delivery)

    body = (
        _WebhookPayload(
            delivery_id=delivery_id,
            task_id=task_id,
            workspace_id=ws_uuid,
            completed_at=completed_at,
            external_ref=external_ref,
            artefact=_WebhookArtefact(content=artifact),
        )
        .model_dump_json()
        .encode()
    )

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if webhook_secret:
        headers["X-Apprise-Signature"] = f"sha256={_sign_body(body, webhook_secret)}"

    success = False
    http_status: int | None = None
    last_error: str | None = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                target_url,
                content=body,
                headers=headers,
            )
        http_status = resp.status_code
        success = resp.status_code < 300
        if not success:
            last_error = f"HTTP {resp.status_code}"
    except Exception as exc:
        last_error = str(exc)
        logger.exception("deliver_webhook: HTTP POST failed for delivery=%s", delivery_id)

    try:
        async with get_session() as session:
            result = await session.execute(
                select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
            )
            record = result.scalar_one_or_none()
            if record is None:
                return

            record.attempt_count += 1
            record.last_attempt_at = datetime.now(UTC)
            record.last_http_status = http_status
            record.last_error = last_error

            if success:
                record.status = "sent"
            else:
                idx = record.attempt_count - 1
                if idx < len(_RETRY_DELAYS):
                    delay = _RETRY_DELAYS[idx]
                    record.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
                    await wctx.arq_queue.enqueue_job(
                        "deliver_webhook",
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        delivery_id=delivery_id,
                        _defer_by=timedelta(seconds=delay),
                    )
                else:
                    record.status = "failed"
                    logger.warning(
                        "deliver_webhook: all retries exhausted for delivery=%s",
                        delivery_id,
                    )
    except Exception:
        logger.exception(
            "deliver_webhook: failed to record outcome for delivery=%s",
            delivery_id,
        )
