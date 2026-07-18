from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from api.services.coordination_config_service import (
    CoordinationConfigService,
    SetCoordinationOverrideCommand,
)
from core.config import settings
from core.coordination.config import resolve_coordination_config


def _make_org(config: dict | None = None) -> MagicMock:
    org = MagicMock()
    org.id = uuid.uuid4()
    org.config = config
    return org


def _make_workspace(organisation_id: uuid.UUID, config: dict | None = None) -> MagicMock:
    ws = MagicMock()
    ws.id = uuid.uuid4()
    ws.organisation_id = organisation_id
    ws.config = config
    return ws


async def test_get_for_org_rejects_malformed_persisted_coordination_config():
    org_repo = AsyncMock()
    workspace_repo = AsyncMock()
    service = CoordinationConfigService(org_repo, workspace_repo)

    for config in ([], {"coordination": []}):
        org = _make_org(config=config)

        with pytest.raises(ValueError, match="mapping"):
            await service.get_for_org(org)


async def test_get_for_workspace_matches_calling_resolver_directly():
    org = _make_org(config={"coordination": {"max_delegation_depth": 4}})
    ws = _make_workspace(org.id, config={"coordination": {"decompose_difficulty_threshold": 3.5}})

    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org
    workspace_repo = AsyncMock()
    service = CoordinationConfigService(org_repo, workspace_repo)

    data = await service.get_for_workspace(ws)

    expected = resolve_coordination_config(
        settings.coordination,
        {"max_delegation_depth": 4},
        {"decompose_difficulty_threshold": 3.5},
    )
    assert data.effective_max_delegation_depth == expected.max_delegation_depth
    assert data.effective_decompose_difficulty_threshold == expected.decompose_difficulty_threshold
    assert data.max_delegation_depth_source == "org"
    assert data.decompose_difficulty_threshold_source == "workspace"


async def test_set_workspace_override_only_touches_the_targeted_key():
    """Regression test for the JSONB-clobber footgun: writing one coordination
    field must not disturb unrelated config keys or the other coordination field."""
    org = _make_org(config=None)
    ws = _make_workspace(
        org.id,
        config={
            "other_key": "x",
            "coordination": {"future_key": "keep", "max_delegation_depth": 3},
        },
    )

    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org
    workspace_repo = AsyncMock()
    # set_workspace_override re-fetches under a row lock rather than trusting
    # the `ws` object passed in — see CoordinationConfigService.set_workspace_override.
    workspace_repo.get_for_update.return_value = ws
    service = CoordinationConfigService(org_repo, workspace_repo)

    cmd = SetCoordinationOverrideCommand(
        max_delegation_depth=None,
        max_delegation_depth_set=False,
        decompose_difficulty_threshold=3.5,
        decompose_difficulty_threshold_set=True,
    )
    await service.set_workspace_override(ws, cmd)

    assert ws.config["other_key"] == "x"
    assert ws.config["coordination"]["max_delegation_depth"] == 3
    assert ws.config["coordination"]["future_key"] == "keep"
    assert ws.config["coordination"]["decompose_difficulty_threshold"] == 3.5
    workspace_repo.get_for_update.assert_awaited_once_with(ws.id)
    workspace_repo.save.assert_awaited_once_with(ws)


async def test_set_workspace_override_explicit_clear_removes_the_key():
    org = _make_org(config=None)
    ws = _make_workspace(
        org.id,
        config={"coordination": {"max_delegation_depth": 2, "decompose_difficulty_threshold": 3.0}},
    )

    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org
    workspace_repo = AsyncMock()
    workspace_repo.get_for_update.return_value = ws
    service = CoordinationConfigService(org_repo, workspace_repo)

    cmd = SetCoordinationOverrideCommand(
        max_delegation_depth=None,
        max_delegation_depth_set=True,  # explicit null — clear back to inherited
        decompose_difficulty_threshold=None,
        decompose_difficulty_threshold_set=False,  # omitted — leave untouched
    )
    await service.set_workspace_override(ws, cmd)

    assert "max_delegation_depth" not in ws.config["coordination"]
    assert ws.config["coordination"]["decompose_difficulty_threshold"] == 3.0


async def test_set_org_override_re_fetches_under_row_lock_not_the_passed_in_object():
    """org.config must come from the locked re-fetch, not the (possibly stale)
    object require_organisation() loaded earlier in the request — otherwise a
    concurrent write to an unrelated key would be clobbered by this save."""
    org = _make_org(config={"other_key": "x", "coordination": {"max_delegation_depth": 2}})
    org_repo = AsyncMock()
    org_repo.get_for_update.return_value = org
    workspace_repo = AsyncMock()
    service = CoordinationConfigService(org_repo, workspace_repo)

    cmd = SetCoordinationOverrideCommand(
        max_delegation_depth=None,
        max_delegation_depth_set=False,
        decompose_difficulty_threshold=3.5,
        decompose_difficulty_threshold_set=True,
    )
    await service.set_org_override(org, cmd)

    assert org.config["other_key"] == "x"
    assert org.config["coordination"]["max_delegation_depth"] == 2
    assert org.config["coordination"]["decompose_difficulty_threshold"] == 3.5
    org_repo.get_for_update.assert_awaited_once_with(org.id)
    org_repo.save.assert_awaited_once_with(org)
