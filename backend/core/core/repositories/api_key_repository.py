from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.auth import ApiKey


class ApiKeyRepository:
    """Concrete ApiKeyRepository backed by SQLAlchemy AsyncSession.

    API paths: use get(workspace_id, key_id) — workspace ownership enforced in Python
    (after PK load) since ApiKey has no composite unique index on (workspace_id, id).
    Auth paths: use get_by_key_prefix() for bcrypt candidate scan; get_by_id() for revocation.

    Transaction contract: never calls commit(). create() flushes to populate the
    DB-generated id before returning. All other methods never flush.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        organisation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        created_by_user_id: uuid.UUID | None,
        name: str,
        key_hash: str,
        key_prefix: str,
        key_sha256: str,
        scopes: list[str] | None,
        expires_at: datetime | None,
    ) -> ApiKey:
        """Stage and flush — caller needs record.id immediately for the HTTP response."""
        record = ApiKey(
            organisation_id=organisation_id,
            workspace_id=workspace_id,
            created_by_user_id=created_by_user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            key_sha256=key_sha256,
            scopes=scopes,
            expires_at=expires_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, workspace_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey | None:
        """Workspace-scoped PK lookup. Returns None if key belongs to a different workspace."""
        record = await self._session.get(ApiKey, key_id)
        if record is None or record.workspace_id != workspace_id:
            return None
        return record

    async def get_by_id(self, key_id: uuid.UUID) -> ApiKey | None:
        """Unscoped PK lookup — for internal auth paths only (revocation)."""
        return await self._session.get(ApiKey, key_id)

    async def get_by_key_prefix(self, key_prefix: str) -> list[ApiKey]:
        """Non-revoked keys matching prefix — for validate_api_key bcrypt candidate scan."""
        result = await self._session.execute(
            select(ApiKey).where(
                ApiKey.key_prefix == key_prefix,
                ApiKey.revoked.is_(False),
            )
        )
        return list(result.scalars().all())

    async def list_all(self, workspace_id: uuid.UUID) -> list[ApiKey]:
        result = await self._session.execute(
            select(ApiKey)
            .where(ApiKey.workspace_id == workspace_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())
