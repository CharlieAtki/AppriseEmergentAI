from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskUpdatedEvent

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
    execution_path == "self_execute" on the snapshot, so no reflect job is enqueued.

    step_count is no longer passed as a parameter. reflect.py derives it from
    TaskExecution.tool_trace by counting recorded tool invocations.
    """

    arq_queue: ArqRedis

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status") or event.state.status != "completed":
            return
        if event.state.execution_path != "self_execute":
            return
        if event.state.executing_agent_id is None or event.state.quality_score is None:
            return
        if event.state.execution_id is None:
            return

        await self.arq_queue.enqueue_job(
            "reflect",
            agent_id=str(event.state.executing_agent_id),
            task_id=str(event.state.id),
            workspace_id=str(event.state.workspace_id),
            execution_id=str(event.state.execution_id),
            quality_score=event.state.quality_score,
        )
        logger.debug(
            "ReflectJobHandler: enqueued reflect for agent=%s task=%s",
            event.state.executing_agent_id, event.state.id,
        )
