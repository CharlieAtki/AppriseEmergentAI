from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Validates X-API-Key header and injects auth context into request.state.

    Stub implementation: accepts any non-empty key and sets a fixed org_id.
    Full implementation: validate key against Redis-cached bcrypt hash (see
    Notion "Authentication, API Security & Secrets Management"), look up the
    ApiKey row to get real org_id and workspace_id, cache for 5 minutes.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            return JSONResponse({"error": "Unauthorised"}, status_code=401)

        # TODO: validate api_key against DB/Redis cache, load real org_id
        request.state.auth = {
            "org_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
            "auth_type": "api_key",
        }
        return await call_next(request)
