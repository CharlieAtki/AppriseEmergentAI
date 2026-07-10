"""Tests for coordination_config.py's org-level PATCH invalidation fan-out.

No FastAPI TestClient here — see test_bidding_config_router.py's module
docstring for why. This is the first router-level test for this resource,
added to cover a real pre-existing gap: update_org_coordination_config()
previously never invalidated the worker's per-workspace Redis cache at all
(only update_workspace_coordination_config() did), leaving every workspace
under an org serving a stale resolved value for up to the TTL after an org
override change. Fixed alongside this test.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from api.routers.coordination_config import (
    update_org_coordination_config,
    update_workspace_coordination_config,
)
from api.schemas.coordination_config import UpdateCoordinationConfigRequest
from api.services.coordination_config_service import CoordinationConfigData


def _make_org() -> MagicMock:
    org = MagicMock()
    org.id = uuid.uuid4()
    return org


def _make_workspace(organisation_id: uuid.UUID) -> MagicMock:
    ws = MagicMock()
    ws.id = uuid.uuid4()
    ws.organisation_id = organisation_id
    return ws


def _make_data() -> CoordinationConfigData:
    return CoordinationConfigData(
        effective_max_delegation_depth=4,
        effective_decompose_difficulty_threshold=3.5,
        max_delegation_depth_source="org",
        decompose_difficulty_threshold_source="org",
        max_delegation_depth_clamped=False,
        platform_max_delegation_depth_default=3,
        platform_max_delegation_depth_ceiling=5,
        platform_decompose_difficulty_threshold_default=4.0,
        org_max_delegation_depth_override=4,
        org_decompose_difficulty_threshold_override=3.5,
        workspace_max_delegation_depth_override=None,
        workspace_decompose_difficulty_threshold_override=None,
    )


async def test_org_patch_invalidates_every_workspace_cache_key_under_the_org():
    org = _make_org()
    workspaces = [_make_workspace(org.id) for _ in range(3)]

    service = AsyncMock()
    service.set_org_override.return_value = _make_data()
    session = AsyncMock()
    workspace_repo = AsyncMock()
    workspace_repo.list_all.return_value = workspaces
    redis = AsyncMock()

    await update_org_coordination_config(
        body=UpdateCoordinationConfigRequest(max_delegation_depth=4),
        org=org,
        service=service,
        session=session,
        workspace_repo=workspace_repo,
        redis=redis,
    )

    session.commit.assert_awaited_once()
    workspace_repo.list_all.assert_awaited_once_with(org.id)
    redis.delete.assert_awaited_once_with(*(f"coordination_config:{ws.id}" for ws in workspaces))


async def test_org_patch_skips_redis_call_when_org_has_no_workspaces():
    org = _make_org()

    service = AsyncMock()
    service.set_org_override.return_value = _make_data()
    session = AsyncMock()
    workspace_repo = AsyncMock()
    workspace_repo.list_all.return_value = []
    redis = AsyncMock()

    await update_org_coordination_config(
        body=UpdateCoordinationConfigRequest(max_delegation_depth=4),
        org=org,
        service=service,
        session=session,
        workspace_repo=workspace_repo,
        redis=redis,
    )

    redis.delete.assert_not_called()


async def test_workspace_patch_invalidates_only_its_own_cache_key():
    org_id = uuid.uuid4()
    ws = _make_workspace(org_id)

    service = AsyncMock()
    service.set_workspace_override.return_value = _make_data()
    session = AsyncMock()
    redis = AsyncMock()

    await update_workspace_coordination_config(
        body=UpdateCoordinationConfigRequest(max_delegation_depth=4),
        workspace=ws,
        service=service,
        session=session,
        redis=redis,
    )

    session.commit.assert_awaited_once()
    redis.delete.assert_awaited_once_with(f"coordination_config:{ws.id}")
