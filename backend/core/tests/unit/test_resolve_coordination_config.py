from __future__ import annotations

from dataclasses import dataclass

import pytest
from core.coordination.config import resolve_coordination_config


@dataclass(frozen=True)
class _PlatformDefaults:
    max_delegation_depth_default: int = 3
    max_delegation_depth_ceiling: int = 5
    decompose_difficulty_threshold_default: float = 4.0


PLATFORM = _PlatformDefaults()


class TestResolveCoordinationConfig:
    def test_platform_only(self) -> None:
        cfg = resolve_coordination_config(PLATFORM, None, None)
        assert cfg.max_delegation_depth == 3
        assert cfg.decompose_difficulty_threshold == 4.0
        assert cfg.max_delegation_depth_source == "platform"
        assert cfg.decompose_difficulty_threshold_source == "platform"
        assert cfg.max_delegation_depth_clamped is False

    def test_org_override_wins_over_platform(self) -> None:
        cfg = resolve_coordination_config(PLATFORM, {"max_delegation_depth": 4}, None)
        assert cfg.max_delegation_depth == 4
        assert cfg.max_delegation_depth_source == "org"
        assert cfg.decompose_difficulty_threshold_source == "platform"

    def test_workspace_override_wins_over_org_and_platform(self) -> None:
        cfg = resolve_coordination_config(
            PLATFORM,
            {"max_delegation_depth": 4},
            {"max_delegation_depth": 2},
        )
        assert cfg.max_delegation_depth == 2
        assert cfg.max_delegation_depth_source == "workspace"

    def test_depth_override_above_ceiling_is_clamped(self) -> None:
        cfg = resolve_coordination_config(PLATFORM, None, {"max_delegation_depth": 8})
        assert cfg.max_delegation_depth == PLATFORM.max_delegation_depth_ceiling
        assert cfg.max_delegation_depth_clamped is True
        # Source still reports "workspace" — the workspace value won the tier
        # resolution, it was the *value* that got capped, not the provenance.
        assert cfg.max_delegation_depth_source == "workspace"

    def test_depth_override_below_ceiling_passes_through_unclamped(self) -> None:
        cfg = resolve_coordination_config(PLATFORM, None, {"max_delegation_depth": 4})
        assert cfg.max_delegation_depth == 4
        assert cfg.max_delegation_depth_clamped is False

    def test_difficulty_threshold_has_no_ceiling_even_for_large_values(self) -> None:
        """Regression guard: the depth clamp must never leak onto the difficulty
        threshold — a copy-paste of the clamp logic onto the wrong field is a
        realistic bug given how similar the two fields look."""
        cfg = resolve_coordination_config(PLATFORM, None, {"decompose_difficulty_threshold": 999.0})
        assert cfg.decompose_difficulty_threshold == 999.0

    @pytest.mark.parametrize("empty_override", [None, {}])
    def test_empty_and_none_override_are_equivalent(self, empty_override: dict | None) -> None:
        cfg = resolve_coordination_config(PLATFORM, empty_override, empty_override)
        assert cfg.max_delegation_depth == 3
        assert cfg.max_delegation_depth_source == "platform"

    def test_explicit_null_in_override_does_not_crash_and_falls_back(self) -> None:
        """Regression test: our own write path never stores null (the service pops
        the key on explicit clear instead), but this resolver must not crash if
        persisted JSONB ever contains one anyway — e.g. a manual DB edit."""
        cfg = resolve_coordination_config(PLATFORM, {"max_delegation_depth": None}, None)
        assert cfg.max_delegation_depth == 3
        assert cfg.max_delegation_depth_source == "platform"

    def test_explicit_null_in_workspace_override_reports_correct_source(self) -> None:
        """Regression test: a null workspace override must not be misreported as
        source="workspace" just because the key is present — the value actually
        used fell back to org, so the source must say so too."""
        cfg = resolve_coordination_config(
            PLATFORM,
            {"max_delegation_depth": 4},
            {"max_delegation_depth": None},
        )
        assert cfg.max_delegation_depth == 4
        assert cfg.max_delegation_depth_source == "org"
