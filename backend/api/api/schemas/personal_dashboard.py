from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, JsonValue, model_validator


class DashboardPanelType(StrEnum):
    AGENT_POOL = "agent-pool"
    LIVE_FEED = "live-feed"
    AGENT_LANES = "agent-lanes"
    ACTIVE_TASKS = "active-tasks"
    EMERGENCE_SIGNAL = "emergence-signal"
    WORKSPACE_STATS = "workspace-stats"


class DashboardPanelLayout(BaseModel):
    id: uuid.UUID
    panel_type: DashboardPanelType
    x: int = Field(ge=0, le=11)
    y: int = Field(ge=0, le=6)
    w: int = Field(ge=1, le=12)
    h: int = Field(ge=1, le=7)
    min_w: int = Field(ge=1, le=12)
    min_h: int = Field(ge=1, le=7)
    config: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fits_grid(self) -> DashboardPanelLayout:
        if self.min_w > self.w or self.min_h > self.h:
            raise ValueError("panel minimum dimensions cannot exceed its dimensions")
        if self.x + self.w > 12 or self.y + self.h > 7:
            raise ValueError("panel must fit within the 12x7 dashboard grid")
        return self


class PersonalDashboardLayoutRequest(BaseModel):
    pages: list[list[DashboardPanelLayout]] = Field(min_length=1, max_length=20)
    active_page: int = Field(ge=0)

    @model_validator(mode="after")
    def validates_pages(self) -> PersonalDashboardLayoutRequest:
        if self.active_page >= len(self.pages):
            raise ValueError("active_page must refer to an existing page")
        seen_ids: set[uuid.UUID] = set()
        for page in self.pages:
            if len(page) > 50:
                raise ValueError("a dashboard page cannot contain more than 50 panels")
            for index, panel in enumerate(page):
                if panel.id in seen_ids:
                    raise ValueError("panel IDs must be unique across the dashboard")
                seen_ids.add(panel.id)
                for other in page[index + 1 :]:
                    if (
                        panel.x < other.x + other.w
                        and panel.x + panel.w > other.x
                        and panel.y < other.y + other.h
                        and panel.y + panel.h > other.y
                    ):
                        raise ValueError("dashboard panels cannot overlap")
        return self


class PersonalDashboardLayoutResponse(PersonalDashboardLayoutRequest):
    updated_at: datetime | None = None
