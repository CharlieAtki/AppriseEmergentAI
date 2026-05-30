from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.services.auth_service import validate_api_key, validate_clerk_token
from core.database import get_session

EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Resolves caller identity and injects auth context into request.state.auth.

    Two authentication paths:

    X-API-Key header — machine-to-machine (scripts, pipelines, MCP clients).
        Validated via Redis cache (SHA-256 key, 5-min TTL), falling back to a
        bcrypt comparison against Postgres on a cache miss. Sets ApiKeyPayload
        on request.state.auth.

    Authorization: Bearer <jwt> — human user via Clerk.
        authenticate_request_async() verifies the JWT signature locally using
        Clerk's cached public JWKS (no network call per request). The resulting
        payload contains Clerk string IDs (org_id, sub) which validate_clerk_token
        resolves to internal UUIDs via a DB lookup. Sets UserPayload on
        request.state.auth.

    app.state.clerk must be a Clerk SDK instance — set in the FastAPI lifespan.
    Any verification failure in either path returns 401; the error detail is
    intentionally generic to avoid leaking auth internals to callers.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        if api_key := request.headers.get("X-API-Key"):
            try:
                async with get_session() as session:
                    redis = request.app.state.redis
                    payload = await validate_api_key(api_key, redis, session)
            except Exception:
                return JSONResponse({"error": "Unauthorised"}, status_code=401)
            request.state.auth = payload
            return await call_next(request)

        if "Authorization" in request.headers:
            # authenticate_request_async reads the Authorization header from
            # the request directly — no need to extract the token manually.
            # It verifies the JWT signature against Clerk's cached public keys,
            # then returns a RequestState whose payload contains org_id and sub.
            try:
                from clerk_backend_api.security import AuthenticateRequestOptions

                clerk = request.app.state.clerk
                req_state = await clerk.authenticate_request_async(
                    request, AuthenticateRequestOptions()
                )
                if not req_state.is_signed_in or req_state.payload is None:
                    return JSONResponse({"error": "Unauthorised"}, status_code=401)
                async with get_session() as session:
                    payload = await validate_clerk_token(req_state.payload, session)
            except Exception:
                return JSONResponse({"error": "Unauthorised"}, status_code=401)
            request.state.auth = payload
            return await call_next(request)

        return JSONResponse({"error": "Unauthorised"}, status_code=401)