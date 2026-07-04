from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import bcrypt as _bcrypt
from fastapi import HTTPException, status
from pydantic import BaseModel

if TYPE_CHECKING:
    from core.repositories.api_key_repository import ApiKeyRepository
    from core.repositories.org_repository import OrganisationRepository
    from core.repositories.user_repository import UserRepository
    from redis.asyncio import Redis


class ApiKeyPayload(BaseModel):
    workspace_id: uuid.UUID
    org_id: uuid.UUID
    scopes: list[str] | None
    auth_type: Literal["api_key"] = "api_key"


class UserPayload(BaseModel):
    org_id: uuid.UUID
    user_id: uuid.UUID
    auth_type: Literal["user"] = "user"


class WsTicketPayload(BaseModel):
    """Single-use WebSocket connect ticket — cached in Redis with a short TTL.

    AuthMiddleware (BaseHTTPMiddleware) never runs for WebSocket scope, so this is
    the auth mechanism for GET /workspaces/{id}/stream: mint via an authenticated
    HTTP call, redeem exactly once via GETDEL on connect.
    """

    org_id: uuid.UUID
    workspace_id: uuid.UUID


def ws_ticket_key(workspace_id: uuid.UUID, token: str) -> str:
    """Single source of truth for the ws_ticket Redis key — used by both
    WorkspaceStreamService.mint_stream_ticket() (write) and
    require_stream_ticket() (GETDEL). Scoping by workspace_id means a ticket
    presented against the wrong workspace path can't be found, so it's never
    consumed by a mismatched request — validating workspace_id only after GETDEL
    would burn a legitimate ticket without granting access.
    """
    return f"ws_ticket:{workspace_id}:{token}"


def _sha256(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def validate_api_key(
    raw_key: str,
    redis: Redis,
    api_key_repo: ApiKeyRepository,
) -> ApiKeyPayload:
    sha = _sha256(raw_key)
    cache_key = f"apikey_valid:{sha}"

    cached = await redis.get(cache_key)
    if cached:
        return ApiKeyPayload.model_validate_json(cached)

    # Cache miss — validate against Postgres.
    # key_prefix = f"apk_live_{token[:8]}" (set at creation) — narrows the scan to
    # at most a handful of rows; bcrypt.verify is the authoritative check.
    # raw_key format: "apk_live_{token}" — skip the 9-char prefix, take 8 chars of token.
    key_prefix = f"apk_live_{raw_key[9:17]}"
    candidates = await api_key_repo.get_by_key_prefix(key_prefix)

    record = None
    for candidate in candidates:
        if _bcrypt.checkpw(raw_key.encode(), candidate.key_hash.encode()):
            record = candidate
            break

    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    if record.expires_at and record.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")

    payload = ApiKeyPayload(
        workspace_id=record.workspace_id,
        org_id=record.organisation_id,
        scopes=record.scopes,
    )
    await redis.set(cache_key, payload.model_dump_json(), ex=300)

    # Fire-and-forget last_used_at update — don't block the request
    record.last_used_at = datetime.now(UTC)

    return payload


async def validate_clerk_token(
    claims: dict[str, Any],
    org_repo: OrganisationRepository,
    user_repo: UserRepository,
) -> UserPayload:
    clerk_org_id: str = claims.get("org_id", "")
    clerk_user_id: str = claims.get("sub", "")

    org = await org_repo.get_by_external_id("clerk", clerk_org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorised")

    user = await user_repo.get_by_external_id("clerk", clerk_user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorised")

    return UserPayload(org_id=org.id, user_id=user.id)
