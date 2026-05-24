from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CreateApiKeyRequest(BaseModel):
    name: str
    scopes: list[str] = ["tasks:read", "tasks:write"]
    expires_at: datetime | None = None


class ApiKeyCreatedResponse(BaseModel):
    id: uuid.UUID
    key: str          # raw key — shown ONCE, never stored or returned again
    key_prefix: str
    name: str
    scopes: list[str]


class ApiKeyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    key_prefix: str
    name: str
    scopes: list[str] | None
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked: bool
    created_at: datetime | None