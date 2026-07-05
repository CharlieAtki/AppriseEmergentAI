"""Tests for auth dependency factories in api.deps that are plain functions,
testable directly against a mocked Request rather than a full ASGI app.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from api.deps import require_organisation
from fastapi import HTTPException


def _make_request(org_id: uuid.UUID, auth_type: str) -> MagicMock:
    request = MagicMock()
    request.state.auth = MagicMock(org_id=org_id, auth_type=auth_type)
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
        await dep(org_id, request, org_repo)

    assert exc_info.value.status_code == 403
    org_repo.get_by_id.assert_not_called()


async def test_require_organisation_accepts_user_session_for_own_org():
    org_id = uuid.uuid4()
    request = _make_request(org_id, auth_type="user")
    org = MagicMock()
    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org

    dep = require_organisation("write")
    result = await dep(org_id, request, org_repo)

    assert result is org
    org_repo.get_by_id.assert_awaited_once_with(org_id)


async def test_require_organisation_rejects_mismatched_org():
    request = _make_request(uuid.uuid4(), auth_type="user")
    org_repo = AsyncMock()

    dep = require_organisation("write")
    with pytest.raises(HTTPException) as exc_info:
        await dep(uuid.uuid4(), request, org_repo)

    assert exc_info.value.status_code == 401
    org_repo.get_by_id.assert_not_called()
