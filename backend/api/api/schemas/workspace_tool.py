from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class EnableToolRequest(BaseModel):
    config: dict[str, Any] | None = None


class WorkspaceToolResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    namespace: str
    name: str
    display_name: str
    description: str
    category: str
    task_types: list[str]
    config_schema: dict[str, Any] | None
    enabled: bool
    config: dict[str, Any] | None
