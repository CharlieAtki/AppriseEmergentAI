from __future__ import annotations

import logging
import os
import socket
from typing import Any

from worker.context import WorkerContext, get_worker_context, init_worker_context

logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    """ARQ startup hook — runs once when the worker process starts.

    Builds :class:`~worker.context.WorkerContext` (registers vendors/tools,
    syncs DB, compiles graphs, opens Redis connections), registers all event
    handlers on the in-process :class:`~core.eventing.bus.in_process_bus.EventBus`,
    then starts :class:`~worker.subscriber.StreamSubscriber` instances that bridge
    Redis Streams into the in-process bus.

    Handler registration order:

    1. In-process handlers — respond to domain events fired by jobs in this process
       (e.g. :class:`~worker.handlers.rollup.RollupSubtaskHandler` on
       ``TaskUpdatedEvent``).
    2. Stream handlers — respond to cross-process events arriving via Redis Streams,
       deserialized by :class:`~worker.subscriber.StreamSubscriber` into typed
       stream events.
    3. Subscriber registration and start — must come after handlers are bound so the
       first deserialized event always finds its handlers registered.

    Local imports are kept inside this function to avoid circular import risk at
    module load time. The handler modules import from ``core.models``, ``core.database``,
    and other packages that must not be imported before the event loop is running.
    """
    arq_queue = ctx["redis"]  # ARQ provides its ArqRedis pool here
    logger.info("worker startup: building context...")
    wctx = await WorkerContext.build(arq_queue)
    init_worker_context(wctx)
    logger.info("worker startup: context ready, graphs compiled for %d task types", len(wctx.graphs))

    from core.eventing.events.stream_events import CfpIssuedStreamEvent, TaskCompletedStreamEvent, TaskCreatedStreamEvent
    from core.eventing.events.task_events import TaskUpdatedEvent
    from worker.handlers.agent_credit import AgentCreditHandler
    from worker.handlers.bidding import TaskBiddingHandler
    from worker.handlers.cfp import CfpHandler
    from worker.handlers.reflect_job import ReflectJobHandler
    from worker.handlers.rollup import RollupSubtaskHandler
    from worker.handlers.social_memory import SocialMemoryHandler
    from worker.handlers.webhook import WebhookDeliveryHandler
    from worker.subscriber import CFP_STREAM_REGISTRY, TASK_STREAM_REGISTRY, StreamSubscriber

    # In-process handlers: same-process side effects triggered by domain events
    wctx.event_bus.bind(TaskUpdatedEvent, RollupSubtaskHandler(
        arq_queue=wctx.arq_queue,
        publish=wctx.event_bus.apublish,
    ))
    wctx.event_bus.bind(TaskUpdatedEvent, AgentCreditHandler())
    wctx.event_bus.bind(TaskUpdatedEvent, ReflectJobHandler(arq_queue=wctx.arq_queue))
    wctx.event_bus.bind(TaskUpdatedEvent, WebhookDeliveryHandler(arq_queue=wctx.arq_queue))

    # Stream handlers: cross-process events deserialized from Redis Streams
    wctx.event_bus.bind(TaskCreatedStreamEvent, TaskBiddingHandler(redis=wctx.redis, arq_queue=wctx.arq_queue))
    wctx.event_bus.bind(TaskCompletedStreamEvent, SocialMemoryHandler(memory=wctx.memory))
    wctx.event_bus.bind(CfpIssuedStreamEvent, CfpHandler(redis=wctx.redis, arq_queue=wctx.arq_queue))

    logger.info("worker startup: event bus handlers registered")

    # Bridge: Redis Streams → in-process EventBus
    wctx.event_bus.subscribe(StreamSubscriber(
        bus=wctx.bus,
        publish=wctx.event_bus.apublish,
        stream="stream:task",
        group="worker-group",
        consumer=f"worker-{socket.gethostname()}-{os.getpid()}",
        registry=TASK_STREAM_REGISTRY,
        name="task",
    ))
    wctx.event_bus.subscribe(StreamSubscriber(
        bus=wctx.bus,
        publish=wctx.event_bus.apublish,
        stream="stream:cfp",
        group="cfp-group",
        consumer=f"cfp-worker-{socket.gethostname()}-{os.getpid()}",
        registry=CFP_STREAM_REGISTRY,
        name="cfp",
    ))
    await wctx.event_bus.start_subscribers()
    logger.info("worker startup: task subscriber started")


async def shutdown(ctx: dict[str, Any]) -> None:
    """ARQ shutdown hook — runs when the worker process stops.

    Shutdown order matters:

    1. ``stop_subscribers`` — cancels all :class:`~worker.subscriber.StreamSubscriber`
       instances cleanly. No new stream events will be published onto the in-process bus after this.
    2. ``drain_pending`` — awaits all in-flight fire-and-forget handler tasks (e.g. a
       :class:`~worker.handlers.rollup.RollupSubtaskHandler` mid-DB-write). Must run
       before Redis connections close because in-flight handlers may be querying the DB
       or enqueuing ARQ jobs.
    3. ``bus.close`` / ``redis.aclose`` — release Redis connections only after all
       in-flight work is done.
    """
    wctx = get_worker_context()
    await wctx.event_bus.stop_subscribers()
    await wctx.event_bus.drain_pending()
    await wctx.bus.close()
    await wctx.redis.aclose()
    logger.info("worker shutdown complete")
