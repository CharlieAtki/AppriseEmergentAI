from __future__ import annotations

import asyncio
import contextlib
import logging

from worker.context import WorkerContext, get_worker_context, init_worker_context
from worker.subscriber import run_task_subscriber

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    """ARQ startup hook — runs once when the worker process starts.

    Builds WorkerContext (registers vendors/tools, syncs DB, compiles graphs,
    opens Redis connections), then starts the bus subscriber as a background task.
    """
    arq_queue = ctx["redis"]  # ARQ provides its ArqRedis pool here
    logger.info("worker startup: building context...")
    wctx = await WorkerContext.build(arq_queue)
    init_worker_context(wctx)
    logger.info("worker startup: context ready, graphs compiled for 4 task types")

    task = asyncio.create_task(run_task_subscriber())
    ctx["_subscriber_task"] = task
    logger.info("worker startup: task subscriber started")


async def shutdown(ctx: dict) -> None:
    """ARQ shutdown hook — runs when the worker process stops."""
    subscriber_task = ctx.get("_subscriber_task")
    if subscriber_task:
        subscriber_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await subscriber_task

    wctx = get_worker_context()
    await wctx.bus.close()
    await wctx.redis.aclose()
    logger.info("worker shutdown complete")
