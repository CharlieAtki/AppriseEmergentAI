from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from core.config import settings as core_settings
from core.eventing.activity.task_stream_logger import TaskStreamLogger
from core.eventing.bus.in_process_bus import EventBus
from core.eventing.bus.redis_bus import RedisBus
from core.eventing.events.task_events import TaskCreatedEvent
from core.intelligence.llm_router import LLMRouter
from core.intelligence.registry import registry
from core.intelligence.routing_config import resolve_routing
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from redis.asyncio import Redis

from api.handlers.task_bridge import TaskCreatedRedisPublisher
from api.middleware.auth import AuthMiddleware
from api.routers import agents as agents_router
from api.routers import api_keys as api_keys_router
from api.routers import tasks as tasks_router
from api.routers import workspaces as workspaces_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    import core.vendors.anthropic  # noqa: F401 — self-registers models

    if not core_settings.clerk.secret_key.get_secret_value().strip():
        raise ValueError(
            "CLERK__SECRET_KEY is not set — the API cannot verify user JWTs. "
            "Set this environment variable before starting the API process."
        )

    loop = asyncio.get_running_loop()
    bus = EventBus(loop=loop)
    redis_bus = await RedisBus.create(core_settings.redis.url)
    redis = Redis.from_url(core_settings.redis.url, decode_responses=True)
    arq_queue = await create_pool(RedisSettings.from_dsn(core_settings.redis.url))

    from core.vendors.anthropic.provider import AnthropicProvider

    routing = resolve_routing(core_settings.intelligence.routing, None)
    llm_router = LLMRouter(
        vendors={"anthropic": AnthropicProvider(core_settings.anthropic)},
        catalog=registry,
        routing=routing.routing,
        max_concurrent=2,
        force_heuristic_fallback=core_settings.intelligence.force_heuristic_fallback,
    )

    from clerk_backend_api import Clerk

    app.state.bus = bus
    app.state.redis_bus = redis_bus
    app.state.redis = redis
    app.state.llm_router = llm_router
    app.state.arq_queue = arq_queue
    # Clerk SDK instance — used by AuthMiddleware to verify human user JWTs.
    # bearer_auth is the Clerk secret key; the SDK fetches Clerk's public JWKS
    # on first verify call and caches them, so subsequent verifications are local
    # crypto with no network round-trip per request.
    app.state.clerk = Clerk(bearer_auth=core_settings.clerk.secret_key.get_secret_value())

    task_stream_logger = TaskStreamLogger(redis_bus.apublish)
    bus.bind(TaskCreatedEvent, TaskCreatedRedisPublisher(task_stream_logger))

    yield

    await bus.drain_pending()
    await redis_bus.close()
    await redis.aclose()
    await arq_queue.aclose()


app = FastAPI(lifespan=lifespan)
app.add_middleware(AuthMiddleware)


def _custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema.setdefault("components", {})["securitySchemes"] = {
        "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        "BearerAuth": {"type": "http", "scheme": "bearer"},
    }
    schema["security"] = [{"ApiKeyAuth": []}, {"BearerAuth": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _custom_openapi  # type: ignore[method-assign]


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


app.include_router(
    workspaces_router.router,
    prefix="/workspaces",
    tags=["workspaces"],
)
app.include_router(
    agents_router.router,
    prefix="/workspaces/{workspace_id}/agents",
    tags=["agents"],
)
app.include_router(
    api_keys_router.router,
    prefix="/workspaces/{workspace_id}/api-keys",
    tags=["api-keys"],
)
app.include_router(
    tasks_router.router,
    prefix="/workspaces/{workspace_id}/tasks",
    tags=["tasks"],
)
