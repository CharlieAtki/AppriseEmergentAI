from __future__ import annotations

import json
from typing import Any

from core.config import settings as core_settings
from core.database import get_session
from core.repositories.org_repository import OrganisationRepository
from core.repositories.user_repository import UserRepository
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from svix.webhooks import Webhook, WebhookVerificationError

from api.services.clerk_webhook_service import ClerkWebhookEnvelope, ClerkWebhookService

router = APIRouter()


async def _verify_svix(request: Request) -> bytes:
    """Verify Svix HMAC signature and return the raw body bytes.

    Returns bytes so the router handler can parse the body without a second
    stream read — Request.body() can only be consumed once.

    Raises 400 (not 401) on failure: a bad signature means the payload is
    invalid or tampered, not that the caller needs to re-authenticate.
    Svix retries on 5xx only, so 400 correctly stops retry loops.
    """
    body = await request.body()
    secret = core_settings.clerk.webhook_secret.get_secret_value()
    try:
        wh = Webhook(secret)
        wh.verify(body, dict(request.headers))
    except WebhookVerificationError as err:
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from err
    return body


@router.post("/", include_in_schema=False)
async def clerk_webhook(
    body: bytes = Depends(_verify_svix),
) -> Response:
    payload: dict[str, Any] = json.loads(body)
    envelope = ClerkWebhookEnvelope(
        type=payload.get("type", ""),
        data=payload.get("data", {}),
    )

    async with get_session() as session:
        service = ClerkWebhookService(
            org_repo=OrganisationRepository(session),
            user_repo=UserRepository(session),
        )
        await service.handle(envelope)

    return Response(status_code=200)
