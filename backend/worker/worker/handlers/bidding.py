from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.database import get_session
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.stream_events import TaskCreatedStreamEvent
from core.repositories.agent_repository import AgentRepository
from core.repositories.task_repository import TaskRepository

from worker.coordination.bidding import score_and_reserve

if TYPE_CHECKING:
    from arq import ArqRedis
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


@dataclass
class TaskBiddingHandler(EventHandler[TaskCreatedStreamEvent]):
    """Runs algorithmic bidding when a new task appears on Redis Streams.

    Queries all active agents for the workspace, then delegates scoring,
    reservation, and job enqueue to :func:`~worker.coordination.bidding.score_and_reserve`.
    This handler is responsible only for the DB query; all bid logic lives in the
    shared coordination module so ``CfpHandler`` can reuse it without coupling to this class.

    Receives ``redis`` for the SETNX reservation lock and ``arq_queue`` to enqueue
    ``execute_task``. Each call opens a fresh DB session — the handler is stateless
    beyond its constructor arguments.

    Falls through silently if no agent meets the workspace's resolved bid score
    threshold (see ``_resolve_bidding_config`` in ``worker.coordination.bidding``)
    or if another worker wins the reservation race first.
    """

    redis: Redis
    arq_queue: ArqRedis

    async def handle(self, event: TaskCreatedStreamEvent) -> None:
        async with get_session() as session:
            task_repo = TaskRepository(session)
            agent_repo = AgentRepository(session)
            agents = await agent_repo.get_active_for_bidding(event.workspace_id)

            if not agents:
                return

            await score_and_reserve(
                task_repo,
                session,
                agents,
                event.task_id,
                event.workspace_id,
                event.required_skills,
                self.redis,
                self.arq_queue,
            )
