from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tasks import WebhookDelivery


class WebhookDeliveryRepository:
    """Concrete WebhookDeliveryRepository backed by SQLAlchemy AsyncSession.

    WebhookDelivery has an independent lifecycle (pending → sent/failed) driven
    by deliver_webhook.py. Two session blocks operate on the same delivery:

      Session 1: idempotency check (get_by_delivery_id) + create on first attempt.
      Session 2: outcome recording (get_by_delivery_id + mutate, auto-tracked by ORM).

    create() generates delivery_id internally — the repo owns the creation contract.
    No flush in create() because delivery_id is Python-generated and available
    immediately. Caller must capture delivery.delivery_id as a local string inside
    the session block before the context manager exits.

    No save() method — session 2 mutations are auto-tracked by SQLAlchemy since
    the record is loaded from the active session via get_by_delivery_id().

    Transaction contract: never calls commit() or flush(). Callers own the
    transaction boundary via get_session() context managers.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_delivery_id(self, delivery_id: str) -> WebhookDelivery | None:
        """Fetch by stable external dedupe key — for idempotency check and outcome recording."""
        return (
            await self._session.execute(
                select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
            )
        ).scalar_one_or_none()

    async def create(
        self,
        organisation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        task_execution_id: uuid.UUID,
        target_url: str,
    ) -> WebhookDelivery:
        """Create a pending delivery record. Generates delivery_id internally.

        No flush — delivery_id is Python-generated and available immediately on
        the returned object. Caller must capture delivery.delivery_id as a local
        string inside the session block before the context manager exits.
        """
        delivery = WebhookDelivery(
            delivery_id=f"dlv_{uuid.uuid4().hex}",
            organisation_id=organisation_id,
            workspace_id=workspace_id,
            task_execution_id=task_execution_id,
            target_url=target_url,
            status="pending",
        )
        self._session.add(delivery)
        return delivery
