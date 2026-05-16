from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingConfig:
    routing: dict[str, str]  # call_type -> model_id


def resolve_routing(
    platform_defaults: dict[str, str],
    workspace_overrides: dict | None,
) -> RoutingConfig:
    merged = {**platform_defaults, **(workspace_overrides or {})}
    return RoutingConfig(routing=merged)
