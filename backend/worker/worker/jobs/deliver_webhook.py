from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from core.database import get_session
from core.models.tasks import Task, TaskExecution, WebhookDelivery
from core.models.tenant import Workspace

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [30, 300, 1800, 7200]  # 30s, 5m, 30m, 2h


async def deliver_webhook(
    ctx,
    execution_id: str,
    workspace_id: str,
    delivery_id: str | None = None,
) -> None:
    """HTTP POST a task-completed webhook payload to the workspace's result_webhook_url.

    On the first invocation delivery_id is None and a new WebhookDelivery row is
    created. On retries the same delivery_id is passed so we update the existing
    row rather than creating a duplicate.

    webhook_secret is stored as plaintext in the DB — this is intentional. HMAC
    requires the raw secret to sign each delivery; unlike a password, it can never
    be stored as a one-way hash. Treat webhook_secret as a credential: never expose
    it in API responses and mask it in logs.
    """
    exec_uuid = uuid.UUID(execution_id)
    ws_uuid = uuid.UUID(workspace_id)

    async with get_session() as session:
        execution = await session.get(TaskExecution, exec_uuid)
        workspace = await session.get(Workspace, ws_uuid)

        if execution is None or workspace is None:
            logger.warning(
                "deliver_webhook: execution or workspace not found exec=%s ws=%s",
                execution_id, workspace_id,
            )
            return

        if not workspace.result_webhook_url:
            return

        # Capture everything we need before the session closes
        target_url: str = workspace.result_webhook_url
        webhook_secret: str | None = workspace.webhook_secret
        org_id = execution.organisation_id
        task_id = execution.task_id
        completed_at = execution.completed_at
        artifact_uri = execution.artifact_uri

        external_ref = None
        if task_id:
            task = await session.get(Task, task_id)
            if task:
                external_ref = task.external_ref

        if delivery_id is None:
            # First attempt — create the delivery record
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

    payload = {
        "delivery_id": delivery_id,
        "event": "task.completed",
        "task_id": str(task_id),
        "workspace_id": workspace_id,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "external_ref": external_ref,
        "artefact": {"type": "text", "content": artifact_uri},
    }
    body = json.dumps(payload).encode()

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if webhook_secret:
        sig = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Apprise-Signature"] = f"sha256={sig}"

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

    async with get_session() as session:
        result = await session.execute(
            select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return

        record.attempt_count += 1
        record.last_attempt_at = datetime.now(timezone.utc)
        record.last_http_status = http_status
        record.last_error = last_error

        if success:
            record.status = "sent"
        else:
            idx = record.attempt_count - 1
            if idx < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[idx]
                record.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                arq_queue = ctx["redis"]
                await arq_queue.enqueue_job(
                    "deliver_webhook",
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    delivery_id=delivery_id,
                    _defer_by=timedelta(seconds=delay),
                )
            else:
                record.status = "failed"
                logger.warning(
                    "deliver_webhook: all retries exhausted for delivery=%s", delivery_id,
                )