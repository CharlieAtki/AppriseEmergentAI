from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from core.database import get_session
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskUpdatedEvent
from core.models.tasks import TaskExecution

if TYPE_CHECKING:
    from arq import ArqRedis

logger = logging.getLogger(__name__)


@dataclass
class ReflectJobHandler(EventHandler[TaskUpdatedEvent]):
    """Enqueues a reflect ARQ job after a self-execute task completes.

    The reflect job runs an LLM call to extract generalised procedural knowledge
    from the execution and apply skill deltas to the agent. It is deliberately
    separate from execute_task — LLM reflection is not on the critical path of
    task completion and should not add latency to the executing job.

    Only fires for the self-execute path. Decompose and CFP executions have no
    quality_score, so no reflect job is enqueued for them — there is nothing
    to reflect on when the agent delegated rather than executed.

    step_count is no longer passed as a parameter. reflect.py derives it from
    TaskExecution.tool_trace by counting recorded tool invocations. This removes
    the dependency on ephemeral LangGraph state that only existed in execute_task's
    memory.
    """

    arq_queue: ArqRedis

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status") or event.state.status != "completed":
            return
        if event.state.executing_agent_id is None:
            return

        async with get_session() as session:
            result = await session.execute(
                select(TaskExecution)
                .where(
                    TaskExecution.task_id == event.state.id,
                    TaskExecution.status == "completed",
                    TaskExecution.agent_id == event.state.executing_agent_id,
                )
                .order_by(TaskExecution.completed_at.desc())
                .limit(1)
            )
            execution = result.scalar_one_or_none()

        if execution is None or execution.quality_score is None:
            return

        await self.arq_queue.enqueue_job(
            "reflect",
            agent_id=str(event.state.executing_agent_id),
            task_id=str(event.state.id),
            workspace_id=str(event.state.workspace_id),
            execution_id=str(execution.id),
            quality_score=execution.quality_score,
        )
        logger.debug(
            "ReflectJobHandler: enqueued reflect for agent=%s task=%s",
            event.state.executing_agent_id, event.state.id,
        )
