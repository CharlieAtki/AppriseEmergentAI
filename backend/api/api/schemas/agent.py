from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class AgentStatus(StrEnum):
    active = "active"
    inactive = "inactive"


class CreateAgentRequest(BaseModel):
    name: str
    personality: dict[str, float] | None = None
    skills: dict[str, float] | None = None


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    status: AgentStatus | None = None


class AgentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    status: AgentStatus
    skills: dict[str, float] | None
    influence: float | None
    created_at: datetime
