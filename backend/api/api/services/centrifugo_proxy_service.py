from __future__ import annotations

import uuid
from dataclasses import dataclass

from core.eventing.activity.workspace_channels import workspace_id_from_events_channel
from core.repositories.org_repository import OrganisationRepository
from core.repositories.user_repository import UserRepository
from fastapi import HTTPException

from api.services.auth_service import validate_clerk_token, verify_clerk_session_token
from api.services.workspace_service import WorkspaceService
from api.services.workspace_stream_service import (
    WorkspaceStreamService,
    WorkspaceStreamSnapshotData,
)


@dataclass(frozen=True)
class ConnectCommand:
    """Router-constructed from the connect-proxy request's `data` field (the
    Clerk session token the browser attached via centrifuge-js's `getData`)."""

    clerk_token: str  # ToDo: Does this need to be external_auth? Lije a ref rather than clerk - leaky abstraction?
    clerk_secret_key: str


@dataclass(frozen=True)
class ConnectResult:
    """user_id becomes Centrifugo's `result.user`; org_id becomes `result.meta.org_id`
    — the org_id must survive to the later subscribe-proxy call (via Centrifugo's
    include_connection_meta forwarding), since a user can belong to more than one
    organisation and org_id is a per-session fact (the Clerk token's active-org
    claim), not something a later lookup by user_id alone could recover."""

    user_id: uuid.UUID
    org_id: uuid.UUID


@dataclass(frozen=True)
class SubscribeCommand:
    """org_id sourced from the subscribe-proxy request's forwarded `meta`
    (set at connect time), not from a fresh DB lookup."""

    org_id: uuid.UUID
    channel: str


@dataclass(frozen=True)
class SubscribeResult:
    snapshot: WorkspaceStreamSnapshotData


class CentrifugoProxyService:
    """Auth/authorization boundary for Centrifugo's connect and subscribe proxy
    callbacks. Commands in, DTOs out — never raises HTTPException (the router
    decides what proxy-protocol envelope to build), never commits a session
    (pure reads)."""

    def __init__(
        self,
        org_repo: OrganisationRepository,
        user_repo: UserRepository,
        workspace_service: WorkspaceService,
        stream_service: WorkspaceStreamService,
    ) -> None:
        self._org_repo = org_repo
        self._user_repo = user_repo
        self._workspace_service = workspace_service
        self._stream_service = stream_service

    async def authenticate_connect(self, cmd: ConnectCommand) -> ConnectResult | None:
        try:
            claims = await verify_clerk_session_token(cmd.clerk_token, cmd.clerk_secret_key)
            payload = await validate_clerk_token(claims, self._org_repo, self._user_repo)
        except HTTPException:
            return None

        return ConnectResult(user_id=payload.user_id, org_id=payload.org_id)

    async def authorize_subscribe(self, cmd: SubscribeCommand) -> SubscribeResult | None:
        workspace_id = workspace_id_from_events_channel(cmd.channel)
        if workspace_id is None:
            return None

        workspace = await self._workspace_service.get_active(cmd.org_id, workspace_id)
        if workspace is None:
            return None

        snapshot = await self._stream_service.get_initial_snapshot(workspace_id)
        return SubscribeResult(snapshot=snapshot)
