from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.config import settings
from core.coordination.contract_net import attempt_reservation, compute_bid_score
from core.coordination.task_state import TaskStateMachine
from core.database import get_session
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.stream_events import CfpIssuedStreamEvent
from core.models.agents import Agent
from core.models.tasks import Task

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
        task_id = str(event.task_id)
        workspace_id = str(event.workspace_id)

        async with get_session() as session:
            agents = (await session.execute(
                select(Agent)
                .where(
                    Agent.workspace_id == event.workspace_id,
                    Agent.status == "active",
                    Agent.id != event.initiating_agent_id,
                )
                .options(selectinload(Agent.task_executions))
            )).scalars().all()

            if not agents:
                return

            scored: list[tuple[Agent, float]] = []
            for agent in agents:
                active = sum(1 for e in agent.task_executions if e.status == "executing")
                score = compute_bid_score(
                    agent_skills=agent.skills or {},
                    agent_influence=agent.influence or 0.0,
                    agent_active_tasks=active,
                    required_skills=event.required_skills,
                    agent_personality=agent.personality,
                    task_domain_tags=event.domain_tags,
                    task_id=task_id,
                    agent_id=str(agent.id),
                )
                if score >= settings.BID_SCORE_THRESHOLD:
                    scored.append((agent, score))

            if not scored:
                logger.debug(
                    "CfpHandler: no agents above threshold for task %s (workspace %s)",
                    task_id, workspace_id,
                )
                return

            scored.sort(key=lambda x: x[1], reverse=True)

            for agent, score in scored:
                won = await attempt_reservation(self.redis, workspace_id, task_id, str(agent.id))
                if won:
                    task = await session.get(Task, event.task_id)
                    if task and task.status == "open":
                        TaskStateMachine.transition(task, "reserved")
                        session.add(task)
                        await self.arq_queue.enqueue_job(
                            "execute_task",
                            agent_id=str(agent.id),
                            task_id=task_id,
                            workspace_id=workspace_id,
                        )
                        logger.info(
                            "CFP task %s reserved by agent %s (score=%.3f, workspace=%s)",
                            task_id, agent.id, score, workspace_id,
                        )
                    break
