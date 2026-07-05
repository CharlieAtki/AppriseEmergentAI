"""Centrifugo connect/subscribe proxy callbacks.

Called by Centrifugo over ordinary server-to-server HTTP, never by the browser
directly — this is what lets Clerk auth run normally (as a plain HTTP request)
for a WebSocket feature, since AuthMiddleware structurally cannot run for
scope["type"] == "websocket". Authenticated by a shared secret
(require_centrifugo_proxy_secret), not Clerk/API-key — see EXEMPT_PREFIXES in
api/middleware/auth.py.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.config import settings as core_settings
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.deps import get_centrifugo_proxy_service, require_centrifugo_proxy_secret
from api.schemas.agent import AgentResponse
from api.schemas.workspace import WorkspaceMetricsResponse, WorkspaceStreamInitEvent
from api.services.centrifugo_proxy_service import (
    CentrifugoProxyService,
    ConnectCommand,
    SubscribeCommand,
)

router = APIRouter(dependencies=[Depends(require_centrifugo_proxy_secret)])


@dataclass(frozen=True)
class CentrifugoConnectRequest:
    """Parsed once at the boundary from Centrifugo's raw connect-proxy JSON
    body — the service and everything downstream only ever sees this, never
    the raw dict."""

    clerk_token: str | None

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> CentrifugoConnectRequest:
        # Frontend's getData() sends {"clerkToken": ...} (useWorkspaceStream.ts) —
        # camelCase because it's a JS-side payload, not one of this app's own
        # snake_case Pydantic schemas; match what's actually sent, not convention.
        data = body.get("data") or {}
        return cls(clerk_token=data.get("clerkToken"))


@dataclass(frozen=True)
class CentrifugoSubscribeRequest:
    """meta is the connect-time metadata Centrifugo forwards here when
    include_connection_meta is enabled (see corrected Decision 10 in the
    migration plan) — this is where org_id survives from connect to subscribe."""

    channel: str
    org_id: uuid.UUID | None

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> CentrifugoSubscribeRequest:
        meta = body.get("meta") or {}
        raw_org_id = meta.get("org_id")
        org_id: uuid.UUID | None
        try:
            org_id = uuid.UUID(raw_org_id) if raw_org_id else None
        except ValueError:
            org_id = None
        return cls(channel=body.get("channel", ""), org_id=org_id)


def _error(code: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}})


@router.post("/connect", include_in_schema=False)
async def centrifugo_connect(
    request: Request,
    service: CentrifugoProxyService = Depends(get_centrifugo_proxy_service),
) -> JSONResponse:
    body = await request.json()
    parsed = CentrifugoConnectRequest.from_body(body)
    if not parsed.clerk_token:
        return _error(401, "missing clerk_token")

    result = await service.authenticate_connect(
        ConnectCommand(
            clerk_token=parsed.clerk_token,
            clerk_secret_key=core_settings.clerk.secret_key.get_secret_value(),
        )
    )
    if result is None:
        return _error(401, "unauthorised")

    return JSONResponse(
        {
            "result": {
                "user": str(result.user_id),
                "meta": {"org_id": str(result.org_id)},
            }
        }
    )


@router.post("/subscribe", include_in_schema=False)
async def centrifugo_subscribe(
    request: Request,
    service: CentrifugoProxyService = Depends(get_centrifugo_proxy_service),
) -> JSONResponse:
    body = await request.json()
    parsed = CentrifugoSubscribeRequest.from_body(body)
    if parsed.org_id is None:
        return _error(403, "forbidden")

    result = await service.authorize_subscribe(
        SubscribeCommand(org_id=parsed.org_id, channel=parsed.channel)
    )
    if result is None:
        return _error(403, "forbidden")

    init_event = WorkspaceStreamInitEvent(
        agents=[AgentResponse.model_validate(agent) for agent in result.snapshot.agents],
        metrics=WorkspaceMetricsResponse.model_validate(result.snapshot.metrics)
        if result.snapshot.metrics is not None
        else None,
    )
    return JSONResponse({"result": {"data": init_event.model_dump(mode="json")}})
