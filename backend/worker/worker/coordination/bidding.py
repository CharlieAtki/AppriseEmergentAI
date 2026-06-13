from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from core.config import settings
from core.coordination.contract_net import attempt_reservation, compute_bid_score
from core.coordination.task_state import TaskStateMachine
from core.models.tasks import Task

if TYPE_CHECKING:
    from arq import ArqRedis
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from core.models.agents import Agent

logger = logging.getLogger(__name__)


async def score_and_reserve(
    session: AsyncSession,
    agents: list[Agent],
    task_id: uuid.UUID,
    workspace_id: uuid.UUID,
    required_skills: dict[str, float] | None,
    domain_tags: dict[str, Any] | None,
    redis: Redis,
    arq_queue: ArqRedis,
) -> None:
    """Score agents, attempt reservation for the highest scorer, enqueue execute_task.

    Pure dispatch — no LLM, no extra DB reads beyond the agent roster the caller
    already loaded. Falls through silently when no agent meets the threshold or when
    another worker wins the SETNX race first.

    Callers are responsible for the DB query and any agent exclusions (e.g. CFP
    excludes the initiating agent before calling this function).
    """
    task_id_str      = str(task_id)
    workspace_id_str = str(workspace_id)

    scored: list[tuple[Agent, float]] = []
    for agent in agents:
        active = sum(1 for e in agent.task_executions if e.status == "executing")
        score = compute_bid_score(
            agent_skills=agent.skills or {},
            agent_influence=agent.influence or 0.0,
            agent_active_tasks=active,
            required_skills=required_skills,
            agent_personality=agent.personality,
            task_domain_tags=domain_tags,
            task_id=task_id_str,
            agent_id=str(agent.id),
        )
        if score >= settings.BID_SCORE_THRESHOLD:
            scored.append((agent, score))

    if not scored:
        return

    scored.sort(key=lambda x: x[1], reverse=True)
    for agent, score in scored:
        won = await attempt_reservation(redis, workspace_id_str, task_id_str, str(agent.id))
        if won:
            task = await session.get(Task, task_id)
            if task and task.status == "open":
                TaskStateMachine.transition(task, "reserved")
                session.add(task)
                await arq_queue.enqueue_job(
                    "execute_task",
                    agent_id=str(agent.id),
                    task_id=task_id_str,
                    workspace_id=workspace_id_str,
                )
                logger.info(
                    "task %s reserved by agent %s (score=%.3f, workspace=%s)",
                    task_id_str, agent.id, score, workspace_id_str,
                )
            break
