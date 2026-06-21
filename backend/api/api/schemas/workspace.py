from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class CreateWorkspaceRequest(BaseModel):
    name: str
    config: dict[str, Any] | None = None


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    status: Literal["active", "paused", "archived"] | None = None
    result_webhook_url: str | None = None
    webhook_secret: str | None = None
    config: dict[str, Any] | None = None


class WorkspaceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    status: str
    result_webhook_url: str | None
    created_at: datetime | None
