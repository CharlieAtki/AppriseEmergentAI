from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from api.services.bidding_config_service import (
    BiddingConfigService,
    SetBiddingOverrideCommand,
)
from core.config import settings
from core.coordination.config import resolve_bidding_config


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


async def test_get_for_org_matches_calling_resolver_directly():
    org = _make_org(config={"bidding": {"bid_score_threshold": 0.5}})

    org_repo = AsyncMock()
    workspace_repo = AsyncMock()
    service = BiddingConfigService(org_repo, workspace_repo)

    data = await service.get_for_org(org)

    expected = resolve_bidding_config(settings.bidding, {"bid_score_threshold": 0.5}, None)
    assert data.effective_bid_score_threshold == expected.bid_score_threshold
    assert data.bid_score_threshold_source == "org"


async def test_get_for_workspace_matches_calling_resolver_directly():
    org = _make_org(config={"bidding": {"bid_score_threshold": 0.4}})
    ws = _make_workspace(org.id, config={"bidding": {"bid_score_threshold": 0.6}})

    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org
    workspace_repo = AsyncMock()
    service = BiddingConfigService(org_repo, workspace_repo)

    data = await service.get_for_workspace(ws)

    expected = resolve_bidding_config(
        settings.bidding, {"bid_score_threshold": 0.4}, {"bid_score_threshold": 0.6}
    )
    assert data.effective_bid_score_threshold == expected.bid_score_threshold
    assert data.bid_score_threshold_source == "workspace"


async def test_set_workspace_override_only_touches_the_bidding_key():
    """Regression test for the JSONB-clobber footgun: writing the bidding
    override must not disturb unrelated config keys, including a sibling
    "coordination" key on the same Workspace.config blob."""
    org = _make_org(config=None)
    ws = _make_workspace(
        org.id,
        config={
            "other_key": "x",
            "coordination": {"max_delegation_depth": 3},
            "bidding": {"bid_score_threshold": 0.2},
        },
    )

    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org
    workspace_repo = AsyncMock()
    service = BiddingConfigService(org_repo, workspace_repo)

    cmd = SetBiddingOverrideCommand(bid_score_threshold=0.9, bid_score_threshold_set=True)
    await service.set_workspace_override(ws, cmd)

    assert ws.config["other_key"] == "x"
    assert ws.config["coordination"]["max_delegation_depth"] == 3
    assert ws.config["bidding"]["bid_score_threshold"] == 0.9
    workspace_repo.save.assert_awaited_once_with(ws)


async def test_set_workspace_override_explicit_clear_removes_the_key():
    org = _make_org(config=None)
    ws = _make_workspace(org.id, config={"bidding": {"bid_score_threshold": 0.2}})

    org_repo = AsyncMock()
    org_repo.get_by_id.return_value = org
    workspace_repo = AsyncMock()
    service = BiddingConfigService(org_repo, workspace_repo)

    cmd = SetBiddingOverrideCommand(bid_score_threshold=None, bid_score_threshold_set=True)
    await service.set_workspace_override(ws, cmd)

    assert "bid_score_threshold" not in ws.config["bidding"]


async def test_set_org_override_only_touches_the_bidding_key():
    org = _make_org(config={"other_key": "y", "coordination": {"max_delegation_depth": 4}})
    org_repo = AsyncMock()
    workspace_repo = AsyncMock()
    service = BiddingConfigService(org_repo, workspace_repo)

    cmd = SetBiddingOverrideCommand(bid_score_threshold=0.8, bid_score_threshold_set=True)
    await service.set_org_override(org, cmd)

    assert org.config["other_key"] == "y"
    assert org.config["coordination"]["max_delegation_depth"] == 4
    assert org.config["bidding"]["bid_score_threshold"] == 0.8
    org_repo.save.assert_awaited_once_with(org)
