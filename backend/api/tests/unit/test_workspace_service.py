"""Tests for WorkspaceService.get_active() — added as part of the Centrifugo
migration (Decision 7) so require_workspace() and the new Centrifugo
subscribe-proxy authorization share one org-ownership + active-status check
instead of duplicating the invariant in two places.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from api.services.workspace_service import WorkspaceService


def _make_workspace(status: str = "active") -> MagicMock:
    ws = MagicMock()
    ws.id = uuid.uuid4()
    ws.organisation_id = uuid.uuid4()
    ws.name = "test"
    ws.status = status
    ws.result_webhook_url = None
    ws.created_at = None
    return ws


async def test_get_active_returns_none_when_workspace_not_found():
    repo = AsyncMock()
    repo.get.return_value = None
    service = WorkspaceService(repo)

    result = await service.get_active(uuid.uuid4(), uuid.uuid4())

    assert result is None


async def test_get_active_returns_none_when_workspace_not_active():
    repo = AsyncMock()
    repo.get.return_value = _make_workspace(status="paused")
    service = WorkspaceService(repo)

    result = await service.get_active(uuid.uuid4(), uuid.uuid4())

    assert result is None


async def test_get_active_returns_data_when_owned_and_active():
    ws = _make_workspace(status="active")
    repo = AsyncMock()
    repo.get.return_value = ws
    service = WorkspaceService(repo)

    result = await service.get_active(ws.organisation_id, ws.id)

    assert result is not None
    assert result.id == ws.id
