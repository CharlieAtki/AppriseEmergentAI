from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CreateAgentRequest(BaseModel):
    name: str
    personality: dict | None = None
    skills: dict | None = None


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    status: Literal["active", "inactive"] | None = None


class AgentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    status: str
    skills: dict | None
    influence: float | None
    created_at: datetime | None