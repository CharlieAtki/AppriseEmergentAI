from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class TaskOverrides(BaseModel):
    task_type: str | None = None
    required_skills: dict[str, float] | None = None
    difficulty: float | None = Field(None, ge=1.0, le=5.0)


class CreateTaskRequest(BaseModel):
    title: str
    description: str | None = None
    task_type: str | None = None
    priority: str | None = None
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

    @field_validator("priority")
    @classmethod
    def priority_enum(cls, v: str | None) -> str | None:
        if v is not None and v not in {"low", "normal", "high", "critical"}:
            raise ValueError("priority must be low, normal, high, or critical")
        return v


class TaskCreatedResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    workspace_id: uuid.UUID


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
    deadline_at: datetime | None
    external_ref: str | None
    idempotency_key: str | None
    required_skills: dict | None
    difficulty: float | None
    domain_tags: dict | None
    created_at: datetime | None
