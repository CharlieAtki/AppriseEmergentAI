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

    Excludes the initiating agent — they already decided to route. Scores all
    other active agents in the workspace with compute_bid_score() (same pure
    function as TaskBiddingHandler), sorts descending, and attempts
    attempt_reservation() for the highest scorer. Winner gets execute_task
    enqueued.

    Falls through silently if no agent qualifies or if another handler wins the
    SETNX race first. The TaskCreatedStreamEvent published by _release_to_pool()
    acts as a safety fallback: if this handler wins nothing, TaskBiddingHandler
    picks up the task via the standard stream:task path.
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
