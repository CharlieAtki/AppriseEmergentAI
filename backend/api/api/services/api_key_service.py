from __future__ import annotations

import hashlib
import secrets
import uuid
from typing import TYPE_CHECKING

import bcrypt as _bcrypt
from core.models.auth import ApiKey
from core.repositories.api_key_repository import ApiKeyRepository

if TYPE_CHECKING:
    from core.models.tenant import Workspace
    from redis.asyncio import Redis

    from api.schemas.api_key import CreateApiKeyRequest


class ApiKeyService:
    def __init__(self, repo: ApiKeyRepository) -> None:
        self._repo = repo

    async def create(
        self,
        workspace: Workspace,
        user_id: uuid.UUID | None,
        body: CreateApiKeyRequest,
    ) -> tuple[ApiKey, str]:
        """Create a new API key and return the ORM record alongside the raw key.

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
            organisation_id=workspace.organisation_id,
            workspace_id=workspace.id,
            created_by_user_id=user_id,
            name=body.name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            key_sha256=key_sha256,
            scopes=body.scopes,
            expires_at=body.expires_at,
        )
        return record, full_key

    async def list(self, workspace_id: uuid.UUID) -> list[ApiKey]:
        return await self._repo.list(workspace_id=workspace_id)

    async def get(self, workspace_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey | None:
        return await self._repo.get(workspace_id=workspace_id, key_id=key_id)

    async def revoke(self, key: ApiKey, redis: Redis) -> None:
        key.revoked = True
        if key.key_sha256:
            await redis.delete(f"apikey_valid:{key.key_sha256}")
