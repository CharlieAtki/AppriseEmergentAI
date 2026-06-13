from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import get_session
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.stream_events import CfpIssuedStreamEvent
from core.models.agents import Agent
from worker.coordination.bidding import score_and_reserve

if TYPE_CHECKING:
    from arq import ArqRedis
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


@dataclass
class CfpHandler(EventHandler[CfpIssuedStreamEvent]):
    """Runs targeted bidding when a CFP event arrives on stream:cfp.

    Identical to ``TaskBiddingHandler`` except the DB query excludes the initiating
    agent (they already decided to route and must not bid on their own task).
    Scoring, reservation, and job enqueue are handled by
    :func:`~worker.coordination.bidding.score_and_reserve`.

    Falls through silently if no agent qualifies or if another worker wins the
    SETNX race first. ``_release_to_pool()`` also publishes a ``TaskCreatedStreamEvent``
    as a safety fallback — if this handler wins nothing, ``TaskBiddingHandler`` picks
    up the task via the standard stream:task path.
    """

    redis: Redis
    arq_queue: ArqRedis

    async def handle(self, event: CfpIssuedStreamEvent) -> None:
        async with get_session() as session:
            agents = (await session.execute(
                select(Agent)
                .where(
                    Agent.workspace_id == event.workspace_id,
                    Agent.status == "active",
                    Agent.id != event.initiating_agent_id,  # excludes the routing agent
                )
                .options(selectinload(Agent.task_executions))
            )).scalars().all()

            if not agents:
                return

            await score_and_reserve(
                session,
                list(agents),
                event.task_id,
                event.workspace_id,
                event.required_skills,
                event.domain_tags,
                self.redis,
                self.arq_queue,
            )
