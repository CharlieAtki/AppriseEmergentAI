from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "BiddingConfigResponse",
    "UpdateBiddingConfigRequest",
]


class UpdateBiddingConfigRequest(BaseModel):
    """Partial update — a field absent from the request body leaves that
    override untouched; a field present with `null` clears it back to
    inherited. The router distinguishes these via `model_fields_set`."""

    bid_score_threshold: float | None = Field(default=None, ge=0, le=1)


class BiddingConfigResponse(BaseModel):
    model_config = {"from_attributes": True}

    effective_bid_score_threshold: float
    bid_score_threshold_source: Literal["platform", "org", "workspace"]
    platform_bid_score_threshold_default: float
    org_bid_score_threshold_override: float | None
    workspace_bid_score_threshold_override: float | None
