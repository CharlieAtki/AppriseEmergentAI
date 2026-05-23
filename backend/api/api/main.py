from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.eventing.bus.in_process_bus import EventBus


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    bus = EventBus(loop=loop)
    app.state.bus = bus
    # Register API-side handlers here when they exist (audit log, cache invalidation, etc.)
    yield
    await bus.drain_pending()


app = FastAPI(lifespan=lifespan)
