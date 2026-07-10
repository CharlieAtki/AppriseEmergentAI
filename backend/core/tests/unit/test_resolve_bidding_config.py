from __future__ import annotations

from dataclasses import dataclass

import pytest
from core.coordination.config import resolve_bidding_config


@dataclass(frozen=True)
class _PlatformDefaults:
    bid_score_threshold_default: float = 0.3


PLATFORM = _PlatformDefaults()


class TestResolveBiddingConfig:
    def test_platform_only(self) -> None:
        cfg = resolve_bidding_config(PLATFORM, None, None)
        assert cfg.bid_score_threshold == 0.3
        assert cfg.bid_score_threshold_source == "platform"

    def test_org_override_wins_over_platform(self) -> None:
        cfg = resolve_bidding_config(PLATFORM, {"bid_score_threshold": 0.5}, None)
        assert cfg.bid_score_threshold == 0.5
        assert cfg.bid_score_threshold_source == "org"

    def test_workspace_override_wins_over_org_and_platform(self) -> None:
        cfg = resolve_bidding_config(
            PLATFORM,
            {"bid_score_threshold": 0.5},
            {"bid_score_threshold": 0.7},
        )
        assert cfg.bid_score_threshold == 0.7
        assert cfg.bid_score_threshold_source == "workspace"

    def test_no_clamp_even_for_out_of_range_values(self) -> None:
        """Regression guard: unlike max_delegation_depth, this resolver applies no
        ceiling/clamp — values pass through unmodified even outside 0..1. Range
        validation is an API-schema concern (Field(ge=0, le=1)), not resolver-layer."""
        cfg = resolve_bidding_config(PLATFORM, None, {"bid_score_threshold": 999.0})
        assert cfg.bid_score_threshold == 999.0

    @pytest.mark.parametrize("empty_override", [None, {}])
    def test_empty_and_none_override_are_equivalent(self, empty_override: dict | None) -> None:
        cfg = resolve_bidding_config(PLATFORM, empty_override, empty_override)
        assert cfg.bid_score_threshold == 0.3
        assert cfg.bid_score_threshold_source == "platform"

    def test_explicit_null_in_override_does_not_crash_and_falls_back(self) -> None:
        cfg = resolve_bidding_config(PLATFORM, {"bid_score_threshold": None}, None)
        assert cfg.bid_score_threshold == 0.3
        assert cfg.bid_score_threshold_source == "platform"

    def test_explicit_null_in_workspace_override_reports_correct_source(self) -> None:
        cfg = resolve_bidding_config(
            PLATFORM,
            {"bid_score_threshold": 0.5},
            {"bid_score_threshold": None},
        )
        assert cfg.bid_score_threshold == 0.5
        assert cfg.bid_score_threshold_source == "org"
