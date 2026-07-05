from __future__ import annotations

from dataclasses import dataclass

from core.utils import merge_tiers


@dataclass(frozen=True)
class RoutingConfig:
    routing: dict[str, str]  # call_type -> model_id


def resolve_routing(
    platform_defaults: dict[str, str],
    workspace_overrides: dict | None,
) -> RoutingConfig:
    return RoutingConfig(routing=merge_tiers(platform_defaults, workspace_overrides))
