from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import bcrypt as _bcrypt
from core.models.auth import ApiKey
from core.repositories.api_key_repository import ApiKeyRepository

if TYPE_CHECKING:
    from redis.asyncio import Redis


@dataclass(frozen=True)
class CreateApiKeyCommand:
    """Immutable write intent — router constructs this from HTTP input; service never imports HTTP schemas."""

    organisation_id: uuid.UUID
    workspace_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    name: str
    scopes: list[str]
    expires_at: datetime | None


@dataclass(frozen=True)
class ApiKeyData:
    """ORM boundary DTO — key_hash and key_sha256 excluded; they are internal security fields, never in responses."""

    id: uuid.UUID
    key_prefix: str
    name: str
    scopes: list[str] | None
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked: bool
    created_at: datetime | None

    @classmethod
    def from_domain(cls, key: ApiKey) -> ApiKeyData:
        return cls(
            id=key.id,
            key_prefix=key.key_prefix,
            name=key.name,
            scopes=key.scopes,
            last_used_at=key.last_used_at,
            expires_at=key.expires_at,
            revoked=key.revoked,
            created_at=key.created_at,
        )


class ApiKeyService:
    """API key lifecycle boundary — accepts Commands, returns ApiKeyData; raw key material never escapes."""

    def __init__(self, repo: ApiKeyRepository) -> None:
        self._repo = repo

    async def create(self, cmd: CreateApiKeyCommand) -> tuple[ApiKeyData, str]:
        """Create a new API key and return the DTO alongside the raw key.

        The raw key is returned once here and never stored — only the bcrypt hash
        persists. key_sha256 is stored so revocation can immediately clear the
        Redis cache entry without needing the original raw key (bcrypt is
        non-deterministic and cannot be used to reconstruct the cache key).
        """
        token = secrets.token_urlsafe(32)
        full_key = f"apk_live_{token}"
        key_hash = _bcrypt.hashpw(full_key.encode(), _bcrypt.gensalt()).decode()
        key_sha256 = hashlib.sha256(full_key.encode()).hexdigest()
        key_prefix = f"apk_live_{token[:8]}"

        record = await self._repo.create(
            organisation_id=cmd.organisation_id,
            workspace_id=cmd.workspace_id,
            created_by_user_id=cmd.created_by_user_id,
            name=cmd.name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            key_sha256=key_sha256,
            scopes=cmd.scopes,
            expires_at=cmd.expires_at,
        )
        return ApiKeyData.from_domain(record), full_key

    async def list(self, workspace_id: uuid.UUID) -> list[ApiKeyData]:
        records = await self._repo.list_all(workspace_id=workspace_id)
        return [ApiKeyData.from_domain(r) for r in records]

    async def get(self, workspace_id: uuid.UUID, key_id: uuid.UUID) -> ApiKeyData | None:
        record = await self._repo.get(workspace_id=workspace_id, key_id=key_id)
        return ApiKeyData.from_domain(record) if record is not None else None

    async def revoke(
        self,
        workspace_id: uuid.UUID,
        key_id: uuid.UUID,
        redis: Redis,
    ) -> ApiKeyData | None:
        """Combined use-case: load, mark revoked, and clear the Redis auth cache in one call. Returns None if not found."""
        key = await self._repo.get(workspace_id=workspace_id, key_id=key_id)
        if key is None:
            return None
        key.revoked = True
        if key.key_sha256:
            await redis.delete(f"apikey_valid:{key.key_sha256}")
        return ApiKeyData.from_domain(key)
