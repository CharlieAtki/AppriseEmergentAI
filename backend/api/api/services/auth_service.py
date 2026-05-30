from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, status
from passlib.hash import bcrypt
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.auth import ApiKey
from core.models.tenant import Organisation, User


class ApiKeyPayload(BaseModel):
    workspace_id: uuid.UUID
    org_id: uuid.UUID
    scopes: list[str]
    auth_type: Literal["api_key"] = "api_key"


class UserPayload(BaseModel):
    org_id: uuid.UUID
    user_id: uuid.UUID
    auth_type: Literal["user"] = "user"


def _sha256(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def validate_api_key(
    raw_key: str,
    redis: Redis,
    session: AsyncSession,
) -> ApiKeyPayload:
    sha = _sha256(raw_key)
    cache_key = f"apikey_valid:{sha}"

    cached = await redis.get(cache_key)
    if cached:
        return ApiKeyPayload.model_validate_json(cached)

    # Cache miss — validate against Postgres.
    # key_prefix = f"appr_{raw_key[:8]}" (set at creation) — narrows the scan to
    # at most a handful of rows; bcrypt.verify is the authoritative check.
    key_prefix = f"appr_{raw_key[:8]}"
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.key_prefix == key_prefix,
            ApiKey.revoked.is_(False),
        )
    )
    candidates = result.scalars().all()
    record: ApiKey | None = None
    for candidate in candidates:
        if bcrypt.verify(raw_key, candidate.key_hash):
            record = candidate
            break

    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    if record.expires_at and record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")

    payload = ApiKeyPayload(
        workspace_id=record.workspace_id,
        org_id=record.organisation_id,
        scopes=record.scopes or [],
    )
    await redis.set(cache_key, payload.model_dump_json(), ex=300)

    # Fire-and-forget last_used_at update — don't block the request
    record.last_used_at = datetime.now(timezone.utc)

    return payload


async def validate_clerk_token(
    claims: dict,
    session: AsyncSession,
) -> UserPayload:
    clerk_org_id: str = claims.get("org_id", "")
    clerk_user_id: str = claims.get("sub", "")

    org_result = await session.execute(
        select(Organisation).where(Organisation.clerk_org_id == clerk_org_id)
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorised")

    user_result = await session.execute(
        select(User).where(User.clerk_user_id == clerk_user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorised")

    return UserPayload(org_id=org.id, user_id=user.id)


async def revoke_api_key(
    key_id: uuid.UUID,
    session: AsyncSession,
    redis: Redis,
) -> None:
    """Revoke an API key and immediately invalidate its Redis cache entry.

    Sets revoked=True in Postgres, then deletes the cached validation result
    so the revocation takes effect on the next request rather than after the
    5-minute cache TTL.

    key_sha256 may be None for keys created before migration 005. Those keys
    fall back to eventual-consistency revocation via the TTL — the DB flag is
    still set correctly and will catch any cache-miss validation.
    """
    record = await session.get(ApiKey, key_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    record.revoked = True
    await session.commit()
    if record.key_sha256:
        await redis.delete(f"apikey_valid:{record.key_sha256}")