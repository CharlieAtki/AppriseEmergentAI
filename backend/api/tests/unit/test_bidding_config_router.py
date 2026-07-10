"""Tests for bidding_config.py's org-level PATCH invalidation fan-out.

No FastAPI TestClient here — this codebase's convention (see
test_centrifugo_proxy_router.py) is direct unit testing of router handler
functions with mocked deps, not full ASGI app fixtures.

This is the first router-level test for either the bidding-config or
coordination-config resource — added specifically to cover the org-level
Redis-invalidation fan-out (the org override affects every workspace under
it, so invalidation must enumerate workspaces rather than delete a single
org-keyed entry nothing reads from). No test previously caught this gap on
the coordination-config router; that gap is fixed alongside this router in
the same change (see coordination_config.py's update_org_coordination_config).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from api.routers.bidding_config import update_org_bidding_config, update_workspace_bidding_config
from api.schemas.bidding_config import UpdateBiddingConfigRequest
from api.services.bidding_config_service import BiddingConfigData


def _make_org() -> MagicMock:
    org = MagicMock()
    org.id = uuid.uuid4()
    return org


def _make_workspace(organisation_id: uuid.UUID) -> MagicMock:
    ws = MagicMock()
    ws.id = uuid.uuid4()
    ws.organisation_id = organisation_id
    return ws


def _make_data() -> BiddingConfigData:
    return BiddingConfigData(
        effective_bid_score_threshold=0.5,
        bid_score_threshold_source="org",
        platform_bid_score_threshold_default=0.3,
        org_bid_score_threshold_override=0.5,
        workspace_bid_score_threshold_override=None,
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

    await update_org_bidding_config(
        body=UpdateBiddingConfigRequest(bid_score_threshold=0.5),
        org=org,
        service=service,
        session=session,
        workspace_repo=workspace_repo,
        redis=redis,
    )

    session.commit.assert_awaited_once()
    workspace_repo.list_all.assert_awaited_once_with(org.id)
    redis.delete.assert_awaited_once_with(*(f"bidding_config:{ws.id}" for ws in workspaces))


async def test_org_patch_skips_redis_call_when_org_has_no_workspaces():
    """Regression guard: redis.delete() with zero args deletes nothing but
    still round-trips to Redis — skip the call entirely when there's nothing
    to invalidate, rather than issuing a no-op command on every org PATCH."""
    org = _make_org()

    service = AsyncMock()
    service.set_org_override.return_value = _make_data()
    session = AsyncMock()
    workspace_repo = AsyncMock()
    workspace_repo.list_all.return_value = []
    redis = AsyncMock()

    await update_org_bidding_config(
        body=UpdateBiddingConfigRequest(bid_score_threshold=0.5),
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

    await update_workspace_bidding_config(
        body=UpdateBiddingConfigRequest(bid_score_threshold=0.5),
        workspace=ws,
        service=service,
        session=session,
        redis=redis,
    )

    session.commit.assert_awaited_once()
    redis.delete.assert_awaited_once_with(f"bidding_config:{ws.id}")
