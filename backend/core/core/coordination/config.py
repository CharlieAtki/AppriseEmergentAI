"""Tiered (platform -> org -> workspace) config resolvers for the ContractNet
coordination package — not "coordination-guards-only" despite the filename
matching CoordinationConfig below. This file is organized by mechanism (pure
tiered-merge resolution via merge_tiers()), not by knob, the same way
contract_net.py already mixes compute_bid_score() (bid-scoring math) and
attempt_reservation() (a reservation primitive) in one file because they're
both "ContractNet coordination logic," not because they're the same concern.
resolve_bidding_config() lives here for that reason: it shares this file's
ConfigSource/_source_of() machinery, and splitting it into its own file would
just force a private cross-file import for zero benefit.

Contrast this with core/config/coordination.py vs core/config/bidding.py,
which ARE kept in separate files — those are BaseSettings subclasses, where
the file boundary maps 1:1 onto an operator-facing env_prefix namespace (a
real external contract), so merging them would leak a naming collision into
env var names. Same package, two different axes, two different answers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from core.utils import merge_tiers

ConfigSource = Literal["platform", "org", "workspace"]


@dataclass(frozen=True)
class CoordinationConfig:
    """Resolved ContractNet coordination guards, with provenance for display."""

    max_delegation_depth: int
    decompose_difficulty_threshold: float
    max_delegation_depth_source: ConfigSource
    decompose_difficulty_threshold_source: ConfigSource
    max_delegation_depth_clamped: bool


def _source_of(
    key: str, org_override: Mapping[str, Any], workspace_override: Mapping[str, Any]
) -> ConfigSource:
    if key in workspace_override:
        return "workspace"
    if key in org_override:
        return "org"
    return "platform"


def resolve_coordination_config(
    platform: Any,
    org_override: Mapping[str, Any] | None,
    workspace_override: Mapping[str, Any] | None,
) -> CoordinationConfig:
    """Resolve platform -> org -> workspace coordination overrides (workspace wins).

    `max_delegation_depth` is clamped to `platform.max_delegation_depth_ceiling`
    regardless of tier — it is the only hard stop against infinite recursion, so
    org/workspace cannot raise it past the platform-set ceiling. No equivalent
    clamp applies to `decompose_difficulty_threshold` — it isn't a safety net,
    just a tuning knob, so it is a plain override with no ceiling.

    An explicit `null` for a key is treated the same as the key being absent —
    our own write path never stores null (CoordinationConfigService pops the key
    on explicit clear instead), but this resolver reads persisted JSONB that
    could in principle contain one (a manual DB edit, a future direct-write path),
    and this runs on the worker's per-task hot path — falling back to the next
    tier is far preferable to crashing every task evaluation in that workspace.
    """
    org_override = {k: v for k, v in (org_override or {}).items() if v is not None}
    workspace_override = {k: v for k, v in (workspace_override or {}).items() if v is not None}

    platform_defaults = {
        "max_delegation_depth": platform.max_delegation_depth_default,
        "decompose_difficulty_threshold": platform.decompose_difficulty_threshold_default,
    }
    merged = merge_tiers(platform_defaults, org_override, workspace_override)

    requested_depth = merged["max_delegation_depth"]
    effective_depth = min(requested_depth, platform.max_delegation_depth_ceiling)

    return CoordinationConfig(
        max_delegation_depth=effective_depth,
        decompose_difficulty_threshold=merged["decompose_difficulty_threshold"],
        max_delegation_depth_source=_source_of(
            "max_delegation_depth", org_override, workspace_override
        ),
        decompose_difficulty_threshold_source=_source_of(
            "decompose_difficulty_threshold", org_override, workspace_override
        ),
        max_delegation_depth_clamped=effective_depth != requested_depth,
    )


@dataclass(frozen=True)
class BiddingConfig:
    """Resolved ContractNet bid-scoring guards, with provenance for display."""

    bid_score_threshold: float
    bid_score_threshold_source: ConfigSource


def resolve_bidding_config(
    platform: Any,
    org_override: Mapping[str, Any] | None,
    workspace_override: Mapping[str, Any] | None,
) -> BiddingConfig:
    """Resolve platform -> org -> workspace bid-scoring overrides (workspace wins).

    Unlike `max_delegation_depth`, `bid_score_threshold` has no ceiling/clamp —
    it's a plain tuning knob (how selective bidding is), not a safety net against
    runaway behaviour, so org/workspace may set it to any value the API schema's
    0..1 range validation allows.
    """
    org_override = {k: v for k, v in (org_override or {}).items() if v is not None}
    workspace_override = {k: v for k, v in (workspace_override or {}).items() if v is not None}

    platform_defaults = {"bid_score_threshold": platform.bid_score_threshold_default}
    merged = merge_tiers(platform_defaults, org_override, workspace_override)

    return BiddingConfig(
        bid_score_threshold=merged["bid_score_threshold"],
        bid_score_threshold_source=_source_of(
            "bid_score_threshold", org_override, workspace_override
        ),
    )
