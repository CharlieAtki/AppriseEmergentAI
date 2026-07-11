from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

__all__ = ["InfluenceHistoryPointResponse", "TaskTimelineEntryResponse"]


class InfluenceHistoryPointResponse(BaseModel):
    """One InfluenceSnapshot row, for the Agent Pool dashboard panel's sparklines."""

    model_config = {"from_attributes": True}

    agent_id: uuid.UUID
    influence: float
    recorded_at: datetime


class TaskTimelineEntryResponse(BaseModel):
    """One TaskExecution row, for the Agent Lanes dashboard panel. Deliberately
    excludes tool_trace/error/execution_path — not needed for a lane chart."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: uuid.UUID
    task_id: uuid.UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
