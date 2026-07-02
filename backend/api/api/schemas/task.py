from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.models.enums import TaskPriority, TaskStatus
from pydantic import BaseModel, Field, field_validator

__all__ = [
    "CreateTaskRequest",
    "TaskCreatedResponse",
    "TaskOverrides",
    "TaskPriority",
    "TaskResponse",
    "TaskStatus",
]


class TaskOverrides(BaseModel):
    task_type: str | None = None
    required_skills: dict[str, float] | None = None
    difficulty: float | None = Field(None, ge=1.0, le=5.0)


class CreateTaskRequest(BaseModel):
    title: str
    description: str | None = None
    task_type: str | None = None
    priority: TaskPriority | None = None
    deadline_at: datetime | None = None
    external_ref: str | None = None
    overrides: TaskOverrides | None = None

    @field_validator("description")
    @classmethod
    def description_min_length(cls, v: str | None) -> str | None:
        if v is not None and len(v.strip()) < 10:
            raise ValueError("description must be at least 10 characters")
        return v

    @field_validator("deadline_at")
    @classmethod
    def deadline_must_be_future(cls, v: datetime | None) -> datetime | None:
        if v is not None and v <= datetime.now(tz=UTC):
            raise ValueError("deadline_at must be in the future")
        return v


class TaskCreatedResponse(BaseModel):
    task_id: uuid.UUID
    status: TaskStatus
    workspace_id: uuid.UUID


class TaskResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    status: TaskStatus
    title: str
    description: str | None
    task_type: str | None
    priority: TaskPriority | None
    deadline_at: datetime | None
    external_ref: str | None
    idempotency_key: str | None
    required_skills: dict[str, float] | None
    difficulty: float | None
    domain_tags: dict[str, Any] | None
    created_at: datetime | None
