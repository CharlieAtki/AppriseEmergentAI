from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CreateTaskRequest(BaseModel):
    title: str
    description: str | None = None
    task_type: str | None = None
    priority: str | None = None
    deadline_at: datetime | None = None
    external_ref: str | None = None
    idempotency_key: str | None = None


class TaskCreatedResponse(BaseModel):
    task_id: uuid.UUID


class TaskResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    status: str
    title: str
    description: str | None
    task_type: str | None
    priority: str | None
    required_skills: dict | None
    difficulty: float | None
    domain_tags: dict | None
    created_at: datetime | None
