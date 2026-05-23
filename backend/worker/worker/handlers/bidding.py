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
from core.eventing.events.stream_events import TaskCreatedStreamEvent
from core.models.agents import Agent
from core.models.tasks import Task

if TYPE_CHECKING:
    from arq import ArqRedis
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


@dataclass
class TaskBiddingHandler(EventHandler[TaskCreatedStreamEvent]):
    """Runs algorithmic bidding when a new task appears on Redis Streams.

    Queries all active agents for the workspace, scores each one with
    :func:`~core.coordination.contract_net.compute_bid_score` (a pure function
    — no LLM, no extra DB reads beyond the initial agent roster), sorts
    descending by score, and attempts a Redis reservation for the highest scorer.
    The first agent to win the reservation lock has an ``execute_task`` job
    enqueued for it.

    Receives ``redis`` for the SETNX reservation lock and ``arq_queue`` to
    enqueue the job. Each call opens a fresh DB session — the handler is
    stateless beyond its constructor arguments.

    Only agents whose score meets or exceeds ``settings.BID_SCORE_THRESHOLD``
    enter the sorted list. If no agent qualifies, the task stays in ``"open"``
    and will be re-evaluated when the next ``task.created`` event arrives (e.g.
    after a CFP re-release).
    """

    redis: Redis
    arq_queue: ArqRedis

    async def handle(self, event: TaskCreatedStreamEvent) -> None:
        task_id = str(event.task_id)
        workspace_id = str(event.workspace_id)

        async with get_session() as session:
            agents = (await session.execute(
                select(Agent)
                .where(Agent.workspace_id == event.workspace_id, Agent.status == "active")
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
                    "no agents above threshold for task %s (workspace %s)",
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
                        "task %s reserved by agent %s (score=%.3f, workspace=%s)",
                        task_id, agent.id, score, workspace_id,
                    )
                    break
