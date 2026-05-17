from __future__ import annotations
import logging

import os
import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.config import settings
from core.coordination.contract_net import attempt_reservation, compute_bid_score
from core.coordination.task_state import TaskStateMachine
from core.database import get_session
from core.models.agents import Agent
from core.models.tasks import Task
from worker.context import WorkerContext, get_worker_context

logger = logging.getLogger(__name__)

_STREAM = "stream:task"
_GROUP  = "worker-group"


async def run_task_subscriber() -> None:
    """Long-running asyncio background task started once in startup().

    Subscribes to stream:task via Redis Streams consumer group. Handles
    task.created events by running algorithmic bidding and enqueuing execute_task
    jobs. Handles task.completed events by triggering social memory updates.

    Never crashes the loop on individual message errors — logs and continues.
    """
    wctx = get_worker_context()
    consumer_name = f"worker-{os.getpid()}"
    logger.info("task subscriber starting (consumer=%s)", consumer_name)

    async for msg_id, payload in wctx.bus.subscribe(_STREAM, _GROUP, consumer_name):
        try:
            event_type = payload.get("event_type", "")
            if event_type == "task.created":
                await _handle_task_created(payload, wctx)
            elif event_type == "task.completed":
                await _handle_task_completed(payload, wctx)
        except Exception:
            logger.exception("subscriber error on message %s: %r", msg_id, payload)
        finally:
            await wctx.bus.ack(_STREAM, _GROUP, msg_id)


async def _handle_task_created(payload: dict, wctx: WorkerContext) -> None:
    workspace_id = payload.get("workspace_id")
    task_id      = payload.get("task_id")
    if not workspace_id or not task_id:
        logger.warning("task.created payload missing workspace_id or task_id: %r", payload)
        return

    async with get_session() as session:
        agents = (await session.execute(
            select(Agent)
            .where(Agent.workspace_id == uuid.UUID(workspace_id), Agent.status == "active")
            .options(selectinload(Agent.task_executions))
        )).scalars().all()

        if not agents:
            return

        # Algorithmic bid scoring — pure function, no LLM, no extra DB reads
        scored: list[tuple[Agent, float]] = []
        for agent in agents:
            active = sum(1 for e in agent.task_executions if e.status == "executing")
            score = compute_bid_score(
                agent_skills=agent.skills or {},
                agent_influence=agent.influence or 0.0,
                agent_active_tasks=active,
                required_skills=payload.get("required_skills") or {},
                agent_personality=agent.personality,
                task_domain_tags=payload.get("domain_tags"),
                task_id=task_id,
                agent_id=str(agent.id),
            )
            if score >= settings.BID_SCORE_THRESHOLD:
                scored.append((agent, score))

        if not scored:
            logger.debug("no agents above threshold for task %s (workspace %s)", task_id, workspace_id)
            return

        # Descending score — highest scorer attempts reservation first
        scored.sort(key=lambda x: x[1], reverse=True)

        for agent, score in scored:
            won = await attempt_reservation(wctx.redis, workspace_id, task_id, str(agent.id))
            if won:
                task = await session.get(Task, uuid.UUID(task_id))
                if task and task.status == "open":
                    TaskStateMachine.transition(task, "reserved")
                    session.add(task)
                # session commits reservation + task status on context manager exit

                await wctx.arq_queue.enqueue_job(
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


async def _handle_task_completed(payload: dict, wctx: WorkerContext) -> None:
    """Store a social memory observation in every peer agent when a task completes."""
    completing_agent_id = payload.get("completing_agent_id")
    workspace_id        = payload.get("workspace_id")
    quality             = payload.get("quality_score", 0.5)
    task_type           = payload.get("task_type", "general")

    if not completing_agent_id or not workspace_id:
        return

    async with get_session() as session:
        peers = (await session.execute(
            select(Agent).where(
                Agent.workspace_id == uuid.UUID(workspace_id),
                Agent.status == "active",
                Agent.id != uuid.UUID(completing_agent_id),
            )
        )).scalars().all()

    for peer in peers:
        await wctx.memory.store_social(
            str(peer.id),
            workspace_id,
            {
                "text": (
                    f"Agent {completing_agent_id} completed a {task_type} task "
                    f"with quality score {quality:.2f}."
                ),
                "observed_agent_id": completing_agent_id,
                "task_type": task_type,
                "quality_score": quality,
            },
        )
