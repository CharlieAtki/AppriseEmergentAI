from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import settings as core_settings
from core.eventing.bus.in_process_bus import EventBus
from core.eventing.bus.redis_bus import RedisBus
from core.eventing.events.task_events import TaskCreatedEvent
from api.handlers.task_bridge import TaskCreatedRedisPublisher
from api.middleware.auth import ApiKeyMiddleware
from api.routers import tasks as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    bus = EventBus(loop=loop)
    redis_bus = await RedisBus.create(core_settings.redis.url)
    app.state.bus = bus
    app.state.redis_bus = redis_bus
    bus.bind(TaskCreatedEvent, TaskCreatedRedisPublisher(redis_bus))
    yield
    await redis_bus.close()
    await bus.drain_pending()


app = FastAPI(lifespan=lifespan)
app.add_middleware(ApiKeyMiddleware)
app.include_router(
    tasks_router.router,
    prefix="/workspaces/{workspace_id}/tasks",
    tags=["tasks"],
)
