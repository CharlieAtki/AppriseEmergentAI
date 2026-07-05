"""Tests for verify_clerk_session_token — the sole place a bare Clerk session
token string (no Request object available) is verified. Used by the Centrifugo
connect proxy; AuthMiddleware's bearer-token path uses a different Clerk SDK
entry point (authenticate_request_async) that flattens v2-token org claims
internally, so this function replicates that flattening for its own callers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from api.services.auth_service import verify_clerk_session_token
from clerk_backend_api.security.types import TokenVerificationError, TokenVerificationErrorReason
from fastapi import HTTPException


async def test_verify_clerk_session_token_returns_claims_on_success():
    with patch(
        "api.services.auth_service.verify_token_async",
        new=AsyncMock(return_value={"sub": "clerk_user", "org_id": "clerk_org"}),
    ):
        claims = await verify_clerk_session_token("tok", "sk")

    assert claims["sub"] == "clerk_user"
    assert claims["org_id"] == "clerk_org"


async def test_verify_clerk_session_token_flattens_v2_nested_org_claim():
    """Real bug caught in live testing: Clerk v2 session tokens carry org info
    nested at claims["o"]["id"], not a flat "org_id" key. Without flattening,
    validate_clerk_token() would silently look up org_id="" and always 401,
    regardless of whether the org actually exists."""
    raw_clerk_claims = {"v": 2, "sub": "clerk_user", "o": {"id": "clerk_org", "rol": "admin"}}
    with patch(
        "api.services.auth_service.verify_token_async",
        new=AsyncMock(return_value=raw_clerk_claims),
    ):
        claims = await verify_clerk_session_token("tok", "sk")

    assert claims["org_id"] == "clerk_org"


async def test_verify_clerk_session_token_does_not_double_flatten_already_flat_org_id():
    raw_clerk_claims = {"v": 2, "sub": "clerk_user", "org_id": "already_flat"}
    with patch(
        "api.services.auth_service.verify_token_async",
        new=AsyncMock(return_value=raw_clerk_claims),
    ):
        claims = await verify_clerk_session_token("tok", "sk")

    assert claims["org_id"] == "already_flat"


async def test_verify_clerk_session_token_does_not_flatten_non_v2_token():
    raw_clerk_claims = {"sub": "clerk_user", "o": {"id": "clerk_org"}}
    with patch(
        "api.services.auth_service.verify_token_async",
        new=AsyncMock(return_value=raw_clerk_claims),
    ):
        claims = await verify_clerk_session_token("tok", "sk")

    assert "org_id" not in claims


async def test_verify_clerk_session_token_raises_http_401_on_invalid_token():
    with patch(
        "api.services.auth_service.verify_token_async",
        new=AsyncMock(
            side_effect=TokenVerificationError(TokenVerificationErrorReason.TOKEN_INVALID)
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await verify_clerk_session_token("bad", "sk")

    assert exc_info.value.status_code == 401
