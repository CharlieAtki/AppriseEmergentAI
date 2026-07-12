"""Tests for CentrifugoProxyService — the auth/authorization boundary for
Centrifugo's connect and subscribe proxy callbacks.

Never raises HTTPException (the router builds the proxy-protocol error
envelope), never commits a session (pure reads) — these tests confirm both
methods collapse every failure mode to a bare None, and that the multi-tenant
authorization in authorize_subscribe actually rejects a workspace the caller's
org doesn't own or that isn't active.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from api.services.auth_service import UserPayload
from api.services.centrifugo_proxy_service import (
    CentrifugoProxyService,
    ConnectCommand,
    SubscribeCommand,
)
from api.services.workspace_stream_service import WorkspaceStreamSnapshotData


def _make_service(workspace_active=True, snapshot=None):
    org_repo = AsyncMock()
    user_repo = AsyncMock()
    workspace_service = AsyncMock()
    workspace_service.get_active.return_value = None if not workspace_active else object()
    stream_service = AsyncMock()
    stream_service.get_initial_snapshot.return_value = snapshot or WorkspaceStreamSnapshotData(
        agents=[], metrics=None
    )
    service = CentrifugoProxyService(org_repo, user_repo, workspace_service, stream_service)
    return service, workspace_service, stream_service


async def test_authenticate_connect_returns_user_and_org_on_success():
    service, _, _ = _make_service()
    user_id, org_id = uuid.uuid4(), uuid.uuid4()

    with (
        patch(
            "api.services.centrifugo_proxy_service.verify_clerk_session_token",
            new=AsyncMock(return_value={"sub": "clerk_user", "org_id": "clerk_org"}),
        ),
        patch(
            "api.services.centrifugo_proxy_service.validate_clerk_token",
            new=AsyncMock(return_value=UserPayload(org_id=org_id, user_id=user_id)),
        ),
    ):
        result = await service.authenticate_connect(
            ConnectCommand(clerk_token="tok", clerk_secret_key="sk")
        )

    assert result is not None
    assert result.user_id == user_id
    assert result.org_id == org_id


async def test_authenticate_connect_returns_none_on_invalid_token():
    """verify_clerk_session_token (auth_service.py) is the sole owner of Clerk
    token verification — it returns None on a TokenVerificationError internally,
    so this service only ever needs a None check, never a Clerk-SDK-specific
    exception type or HTTPException."""
    service, _, _ = _make_service()

    with patch(
        "api.services.centrifugo_proxy_service.verify_clerk_session_token",
        new=AsyncMock(return_value=None),
    ):
        result = await service.authenticate_connect(
            ConnectCommand(clerk_token="bad", clerk_secret_key="sk")
        )

    assert result is None


async def test_authenticate_connect_returns_none_when_clerk_token_valid_but_user_unknown():
    """validate_clerk_token returns None when org/user lookup misses — the
    service must propagate that into its own None, never raise HTTPException
    (services never raise HTTPException)."""
    service, _, _ = _make_service()

    with (
        patch(
            "api.services.centrifugo_proxy_service.verify_clerk_session_token",
            new=AsyncMock(return_value={"sub": "unknown", "org_id": "unknown"}),
        ),
        patch(
            "api.services.centrifugo_proxy_service.validate_clerk_token",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await service.authenticate_connect(
            ConnectCommand(clerk_token="tok", clerk_secret_key="sk")
        )

    assert result is None


async def test_authorize_subscribe_rejects_unparseable_channel():
    service, workspace_service, _ = _make_service()

    result = await service.authorize_subscribe(
        SubscribeCommand(org_id=uuid.uuid4(), channel="not-a-workspace-channel")
    )

    assert result is None
    workspace_service.get_active.assert_not_awaited()


async def test_authorize_subscribe_rejects_trace_channel():
    """Only the dashboard-contract (:events) channel shape is accepted — the
    trace channel has no subscriber today and must not become subscribable
    just because a client asks."""
    service, workspace_service, _ = _make_service()
    workspace_id = uuid.uuid4()

    result = await service.authorize_subscribe(
        SubscribeCommand(org_id=uuid.uuid4(), channel=f"workspace:{workspace_id}:trace")
    )

    assert result is None
    workspace_service.get_active.assert_not_awaited()


async def test_authorize_subscribe_rejects_workspace_the_org_does_not_own_or_inactive():
    service, workspace_service, _ = _make_service(workspace_active=False)
    workspace_id = uuid.uuid4()
    org_id = uuid.uuid4()

    result = await service.authorize_subscribe(
        SubscribeCommand(org_id=org_id, channel=f"workspace:{workspace_id}:events")
    )

    assert result is None
    workspace_service.get_active.assert_awaited_once_with(org_id, workspace_id)


async def test_authorize_subscribe_returns_initial_snapshot_on_success():
    snapshot = WorkspaceStreamSnapshotData(agents=[], metrics=None)
    service, _workspace_service, stream_service = _make_service(
        workspace_active=True, snapshot=snapshot
    )
    workspace_id = uuid.uuid4()
    org_id = uuid.uuid4()

    result = await service.authorize_subscribe(
        SubscribeCommand(org_id=org_id, channel=f"workspace:{workspace_id}:events")
    )

    assert result is not None
    assert result.snapshot is snapshot
    stream_service.get_initial_snapshot.assert_awaited_once_with(workspace_id)
