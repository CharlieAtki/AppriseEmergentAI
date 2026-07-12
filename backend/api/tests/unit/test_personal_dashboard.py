from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from api.schemas.personal_dashboard import PersonalDashboardLayoutRequest
from api.services.personal_dashboard_service import (
    PersonalDashboardService,
    SavePersonalDashboardLayoutCommand,
)
from pydantic import ValidationError


def _panel(**overrides: object) -> dict[str, object]:
    return {
        "id": uuid.uuid4(),
        "panel_type": "agent-pool",
        "x": 0,
        "y": 0,
        "w": 3,
        "h": 2,
        "min_w": 3,
        "min_h": 2,
        "config": {},
        **overrides,
    }


def test_layout_rejects_overlapping_panels():
    with pytest.raises(ValidationError, match="cannot overlap"):
        PersonalDashboardLayoutRequest(pages=[[_panel(), _panel()]], active_page=0)


def test_layout_rejects_a_panel_outside_grid():
    with pytest.raises(ValidationError, match="must fit"):
        PersonalDashboardLayoutRequest(pages=[[_panel(x=10, w=3)]], active_page=0)


async def test_service_returns_empty_layout_when_user_has_no_saved_dashboard():
    repo = AsyncMock()
    repo.get.return_value = None

    result = await PersonalDashboardService(repo).get(uuid.uuid4(), uuid.uuid4())

    assert result.pages == [[]]
    assert result.active_page == 0
    assert result.updated_at is None


async def test_service_saves_the_complete_layout_document():
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    repo = AsyncMock()
    stored = AsyncMock()
    stored.layout = {"pages": [[_panel(id=str(uuid.uuid4()))]]}
    stored.active_page = 0
    stored.updated_at = None
    repo.upsert.return_value = stored
    command = SavePersonalDashboardLayoutCommand(pages=stored.layout["pages"], active_page=0)

    await PersonalDashboardService(repo).save(user_id, workspace_id, command)

    repo.upsert.assert_awaited_once_with(
        user_id=user_id,
        workspace_id=workspace_id,
        layout={"pages": command.pages},
        active_page=0,
    )
