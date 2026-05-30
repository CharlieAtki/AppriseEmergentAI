from __future__ import annotations

import hashlib
import secrets
import uuid
from typing import TYPE_CHECKING

from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.auth import ApiKey
from core.models.tenant import Workspace

from api.services.auth_service import revoke_api_key

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from api.schemas.api_key import CreateApiKeyRequest


class ApiKeyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        raw_key = secrets.token_urlsafe(32)
        key_hash = bcrypt.hash(raw_key)
        key_sha256 = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = f"appr_{raw_key[:8]}"

        record = ApiKey(
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
        self._session.add(record)
        await self._session.flush()
        return record, raw_key

    async def list(self, workspace_id: uuid.UUID) -> list[ApiKey]:
        result = await self._session.execute(
            select(ApiKey)
            .where(ApiKey.workspace_id == workspace_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, workspace_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey | None:
        record = await self._session.get(ApiKey, key_id)
        if record is None or record.workspace_id != workspace_id:
            return None
        return record

    async def revoke(self, key: ApiKey, redis: Redis) -> None:
        await revoke_api_key(key_id=key.id, session=self._session, redis=redis)