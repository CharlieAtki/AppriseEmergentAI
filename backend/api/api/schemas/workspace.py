from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from core.models.enums import WorkspaceStatus
from pydantic import BaseModel

__all__ = [
    "CreateWorkspaceRequest",
    "UpdateWorkspaceRequest",
    "WorkspaceResponse",
    "WorkspaceStatus",
]


class CreateWorkspaceRequest(BaseModel):
    name: str
    config: dict[str, Any] | None = None


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    status: WorkspaceStatus | None = None
    result_webhook_url: str | None = None
    webhook_secret: str | None = None
    config: dict[str, Any] | None = None


class WorkspaceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    status: WorkspaceStatus
    result_webhook_url: str | None
    created_at: datetime | None
    agent_count: int = 0
