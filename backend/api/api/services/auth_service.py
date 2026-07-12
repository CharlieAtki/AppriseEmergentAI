from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import bcrypt as _bcrypt
from clerk_backend_api.security import VerifyTokenOptions, verify_token_async
from clerk_backend_api.security.types import TokenVerificationError
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


def _sha256(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def validate_api_key(
    raw_key: str,
    redis: Redis,
    api_key_repo: ApiKeyRepository,
) -> ApiKeyPayload | None:
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
        return None

    if record.expires_at and record.expires_at < datetime.now(UTC):
        return None

    payload = ApiKeyPayload(
        workspace_id=record.workspace_id,
        org_id=record.organisation_id,
        scopes=record.scopes,
    )
    await redis.set(cache_key, payload.model_dump_json(), ex=300)

    # Fire-and-forget last_used_at update — don't block the request
    record.last_used_at = datetime.now(UTC)

    return payload


async def verify_clerk_session_token(token: str, secret_key: str) -> dict[str, Any] | None:
    """Verifies a bare Clerk session token string (no Request object available —
    used by the Centrifugo connect proxy, which only receives a JSON token, not
    an HTTP request/cookie). AuthMiddleware's bearer-token path goes through
    clerk.authenticate_request_async() instead, which flattens Clerk's v2-token
    org claim (nested at claims["o"]["id"]) into a top-level "org_id" key before
    validate_clerk_token() ever sees it. verify_token_async() skips that
    normalization, so it's replicated here — this is the only place a bare
    token string is verified, so this is the only place that needs to do it."""
    try:
        claims: dict[str, Any] = await verify_token_async(
            token, VerifyTokenOptions(secret_key=secret_key)
        )
    except TokenVerificationError:
        return None

    if claims.get("v") == 2 and "org_id" not in claims:
        org_claims = claims.get("o") or {}
        claims["org_id"] = org_claims.get("id")

    return claims


async def validate_clerk_token(
    claims: dict[str, Any],
    org_repo: OrganisationRepository,
    user_repo: UserRepository,
) -> UserPayload | None:
    clerk_org_id: str = claims.get("org_id", "")
    clerk_user_id: str = claims.get("sub", "")

    org = await org_repo.get_by_external_id("clerk", clerk_org_id)
    if org is None:
        return None

    user = await user_repo.get_by_external_id("clerk", clerk_user_id)
    if user is None:
        return None

    return UserPayload(org_id=org.id, user_id=user.id)
