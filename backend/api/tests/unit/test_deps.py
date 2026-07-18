"""Tests for auth dependency factories in api.deps that are plain functions,
testable directly against a mocked Request rather than a full ASGI app.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.deps import require_organisation, require_workspace
from fastapi import HTTPException


def _make_request(org_id: uuid.UUID, auth_type: str, user_id: uuid.UUID | None = None) -> MagicMock:
    request = MagicMock()
    request.state.auth = MagicMock(org_id=org_id, auth_type=auth_type, user_id=user_id)
    return request


async def test_require_organisation_rejects_api_key_auth():
    """API keys are workspace-scoped credentials — one issued for a single
    workspace must not be able to write org-wide config affecting every other
    workspace in that org. This is a hard boundary, not a roles nuance."""
    org_id = uuid.uuid4()
    request = _make_request(org_id, auth_type="api_key")
    org_repo = AsyncMock()

    dep = require_organisation("write")
    with pytest.raises(HTTPException) as exc_info:
        await dep("org_clerkid123", request, org_repo)

    assert exc_info.value.status_code == 403
    org_repo.get_by_id.assert_not_called()


async def test_require_organisation_accepts_admin_member_for_own_org():
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request = _make_request(org_id, auth_type="user", user_id=user_id)
    org = MagicMock()
    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org
    org_repo.get_member.return_value = MagicMock(role="admin")

    dep = require_organisation("write")
    result = await dep("org_clerkid123", request, org_repo)

    assert result is org
    org_repo.get_by_id.assert_awaited_once_with(org_id)
    org_repo.get_member.assert_awaited_once_with(org_id, user_id)


async def test_require_organisation_rejects_non_admin_member_for_write():
    """A member without a write-capable role must not be able to change
    org-wide config, even though they belong to the organisation."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request = _make_request(org_id, auth_type="user", user_id=user_id)
    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = MagicMock()
    org_repo.get_member.return_value = MagicMock(role="member")

    dep = require_organisation("write")
    with pytest.raises(HTTPException) as exc_info:
        await dep("org_clerkid123", request, org_repo)

    assert exc_info.value.status_code == 403


async def test_require_organisation_allows_non_admin_member_for_read():
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request = _make_request(org_id, auth_type="user", user_id=user_id)
    org = MagicMock()
    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org
    org_repo.get_member.return_value = MagicMock(role="member")

    dep = require_organisation("read")
    result = await dep("org_clerkid123", request, org_repo)

    assert result is org


async def test_require_organisation_rejects_non_member():
    """The caller's org_id/token can be valid while the organisation_members
    row is missing (e.g. Clerk webhook lag) — must not be treated as a member."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request = _make_request(org_id, auth_type="user", user_id=user_id)
    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = MagicMock()
    org_repo.get_member.return_value = None

    dep = require_organisation("write")
    with pytest.raises(HTTPException) as exc_info:
        await dep("org_clerkid123", request, org_repo)

    assert exc_info.value.status_code == 403


async def test_require_organisation_ignores_path_org_id():
    """The `org_id` path segment is Clerk's org id (not our internal UUID) and
    exists for URL readability only — identity comes exclusively from
    request.state.auth.org_id, so an arbitrary/non-matching path value must
    not affect the outcome."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request = _make_request(org_id, auth_type="user", user_id=user_id)
    org = MagicMock()
    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org
    org_repo.get_member.return_value = MagicMock(role="admin")

    dep = require_organisation("write")
    result = await dep("org_totally_different_clerk_id", request, org_repo)

    assert result is org
    org_repo.get_by_id.assert_awaited_once_with(org_id)


async def test_require_organisation_rejects_missing_auth_org_id():
    request = _make_request(None, auth_type="user")
    org_repo = AsyncMock()

    dep = require_organisation("write")
    with pytest.raises(HTTPException) as exc_info:
        await dep("org_clerkid123", request, org_repo)

    assert exc_info.value.status_code == 401
    org_repo.get_by_id.assert_not_called()


# ── require_workspace ─────────────────────────────────────────────────────────


def _workspace_request(org_id: uuid.UUID, *, scopes: list[str] | None = None) -> MagicMock:
    request = MagicMock()
    request.state.auth = MagicMock(org_id=org_id, scopes=scopes)
    return request


def _make_workspace(status: str) -> MagicMock:
    ws = MagicMock()
    ws.status = status
    return ws


async def test_require_workspace_rejects_paused_workspace_by_default():
    """Documents the default (require_active=True) behaviour that routes like
    "create task" rely on to block operating inside a paused workspace."""
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    request = _workspace_request(org_id)
    ws = _make_workspace("paused")

    with patch("api.deps.WorkspaceRepository") as repo_cls:
        repo_cls.return_value.get = AsyncMock(return_value=ws)
        dep = require_workspace("write")
        with pytest.raises(HTTPException) as exc_info:
            await dep(workspace_id, request, AsyncMock())

    assert exc_info.value.status_code == 409


async def test_require_workspace_require_active_false_allows_paused_workspace():
    """Regression test: PATCH /workspaces/{id} (reactivate) and DELETE must be
    reachable on a paused workspace — this is the exact bug that made it
    permanently impossible to flip a paused workspace back to active."""
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    request = _workspace_request(org_id)
    ws = _make_workspace("paused")

    with patch("api.deps.WorkspaceRepository") as repo_cls:
        repo_cls.return_value.get = AsyncMock(return_value=ws)
        dep = require_workspace("write", require_active=False)
        result = await dep(workspace_id, request, AsyncMock())

    assert result is ws


async def test_require_workspace_require_active_false_still_checks_ownership():
    """require_active=False must not bypass the 404-on-not-found/not-owned check."""
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    request = _workspace_request(org_id)

    with patch("api.deps.WorkspaceRepository") as repo_cls:
        repo_cls.return_value.get = AsyncMock(return_value=None)
        dep = require_workspace("write", require_active=False)
        with pytest.raises(HTTPException) as exc_info:
            await dep(workspace_id, request, AsyncMock())

    assert exc_info.value.status_code == 404


async def test_require_workspace_active_workspace_always_allowed():
    org_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    request = _workspace_request(org_id)
    ws = _make_workspace("active")

    with patch("api.deps.WorkspaceRepository") as repo_cls:
        repo_cls.return_value.get = AsyncMock(return_value=ws)
        dep = require_workspace("write")
        result = await dep(workspace_id, request, AsyncMock())

    assert result is ws


async def test_require_user_session_rejects_api_keys():
    from api.deps import require_user_session

    request = MagicMock()
    request.state.auth = MagicMock(auth_type="api_key", user_id=None)

    with pytest.raises(HTTPException) as exc_info:
        require_user_session(request)

    assert exc_info.value.status_code == 403


def test_require_user_session_returns_authenticated_user_id():
    from api.deps import require_user_session

    user_id = uuid.uuid4()
    request = MagicMock()
    request.state.auth = MagicMock(auth_type="user", user_id=user_id)

    assert require_user_session(request) == user_id
