from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

__all__ = [
    "CoordinationConfigResponse",
    "UpdateCoordinationConfigRequest",
]


class UpdateCoordinationConfigRequest(BaseModel):
    """Partial update — a field absent from the request body leaves that
    override untouched; a field present with `null` clears it back to
    inherited. The router distinguishes these via `model_fields_set`."""

    max_delegation_depth: int | None = None
    decompose_difficulty_threshold: float | None = None


class CoordinationConfigResponse(BaseModel):
    model_config = {"from_attributes": True}

    effective_max_delegation_depth: int
    effective_decompose_difficulty_threshold: float
    max_delegation_depth_source: Literal["platform", "org", "workspace"]
    decompose_difficulty_threshold_source: Literal["platform", "org", "workspace"]
    max_delegation_depth_clamped: bool
    platform_max_delegation_depth_default: int
    platform_max_delegation_depth_ceiling: int
    platform_decompose_difficulty_threshold_default: float
    org_max_delegation_depth_override: int | None
    org_decompose_difficulty_threshold_override: float | None
    workspace_max_delegation_depth_override: int | None
    workspace_decompose_difficulty_threshold_override: float | None
