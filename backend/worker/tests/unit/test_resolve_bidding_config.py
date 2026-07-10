"""Tests for worker.coordination.bidding._resolve_bidding_config.

Mirrors test_execute_task.py's cache-hit-focused style for the analogous
_resolve_coordination_config helper: the merge/tier-resolution logic itself is
covered exhaustively in core/tests/unit/test_resolve_bidding_config.py, so
these tests only need to prove the cache-hit short-circuit and the
cache-miss -> DB -> cache-set fallback wire up correctly.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from worker.coordination.bidding import _resolve_bidding_config


async def test_cache_hit_returns_without_touching_the_db():
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=json.dumps(
            {"bid_score_threshold": 0.42, "bid_score_threshold_source": "workspace"}
        )
    )
    session = AsyncMock()

    with (
        patch("worker.coordination.bidding.OrganisationRepository") as org_repo_cls,
        patch("worker.coordination.bidding.WorkspaceRepository") as ws_repo_cls,
    ):
        cfg = await _resolve_bidding_config(redis, session, uuid.uuid4(), uuid.uuid4())

    assert cfg.bid_score_threshold == 0.42
    assert cfg.bid_score_threshold_source == "workspace"
    org_repo_cls.assert_not_called()
    ws_repo_cls.assert_not_called()
    redis.set.assert_not_called()


async def test_cache_miss_resolves_from_db_and_populates_the_cache():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    session = AsyncMock()

    org = MagicMock()
    org.config = {"bidding": {"bid_score_threshold": 0.6}}
    workspace = MagicMock()
    workspace.config = None

    org_repo = AsyncMock()
    org_repo.get_by_id = AsyncMock(return_value=org)
    ws_repo = AsyncMock()
    ws_repo.get_by_id = AsyncMock(return_value=workspace)

    workspace_id = uuid.uuid4()

    with (
        patch("worker.coordination.bidding.OrganisationRepository", return_value=org_repo),
        patch("worker.coordination.bidding.WorkspaceRepository", return_value=ws_repo),
    ):
        cfg = await _resolve_bidding_config(redis, session, uuid.uuid4(), workspace_id)

    assert cfg.bid_score_threshold == 0.6
    assert cfg.bid_score_threshold_source == "org"
    redis.set.assert_awaited_once()
    cache_key, cached_json = redis.set.call_args.args
    assert cache_key == f"bidding_config:{workspace_id}"
    assert json.loads(cached_json)["bid_score_threshold"] == 0.6
