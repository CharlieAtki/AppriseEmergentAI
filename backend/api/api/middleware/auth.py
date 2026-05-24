from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.services.auth_service import validate_api_key, validate_clerk_token

EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Resolves caller identity and injects auth context into request.state.auth.

    Two paths:
    - X-API-Key header → machine-to-machine (scripts, pipelines, MCP clients).
      Validated via Redis cache (SHA-256 key, 5-min TTL) → bcrypt against Postgres
      on cache miss. Sets ApiKeyPayload on request.state.auth.

    - Authorization: Bearer <jwt> → human user via Clerk JWT.
      verify_token() is local crypto (Clerk public keys cached at startup) — no
      network call per request. DB lookup resolves Clerk string IDs → internal UUIDs.
      Sets UserPayload on request.state.auth.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        if api_key := request.headers.get("X-API-Key"):
            from core.database import SessionLocal
            session = SessionLocal()
            try:
                redis = request.app.state.redis
                payload = await validate_api_key(api_key, redis, session)
                await session.commit()
            except Exception:
                await session.rollback()
                return JSONResponse({"error": "Unauthorised"}, status_code=401)
            finally:
                await session.close()
            request.state.auth = payload
            return await call_next(request)

        if bearer := request.headers.get("Authorization", "").removeprefix("Bearer "):
            # Clerk JWT path — local crypto verify (no network call), then DB lookup
            # to resolve Clerk string IDs → internal UUIDs.
            # Requires app.state.clerk (Clerk SDK instance) set in lifespan.
            from core.database import SessionLocal
            session = SessionLocal()
            try:
                clerk = request.app.state.clerk
                claims = clerk.verify_token(bearer)
                payload = await validate_clerk_token(claims, session)
                await session.commit()
            except Exception:
                await session.rollback()
                return JSONResponse({"error": "Unauthorised"}, status_code=401)
            finally:
                await session.close()
            request.state.auth = payload
            return await call_next(request)

        return JSONResponse({"error": "Unauthorised"}, status_code=401)