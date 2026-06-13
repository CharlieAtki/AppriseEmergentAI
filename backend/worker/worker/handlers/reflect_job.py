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
    """Enqueues a reflect ARQ job after a self-execute task completes or fails.

    Fires on both "completed" and "failed" — failure is the most informative learning
    signal and must produce episodic records, skill penalties, and procedural rules.

    Passes only IDs and status to the job. The job loads quality_score directly from
    the TaskExecution row — passing it from the handler would be a SoC violation.

    Only fires for the self-execute path. Decompose and CFP executions have
    execution_path != "self_execute" on the snapshot, so no reflect job is enqueued.
    """

    arq_queue: ArqRedis

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status"):
            return
        if event.state.status not in {"completed", "failed"}:
            return
        if event.state.execution_path != "self_execute":
            return
        if event.state.executing_agent_id is None or event.state.execution_id is None:
            return

        await self.arq_queue.enqueue_job(
            "reflect",
            agent_id=str(event.state.executing_agent_id),
            task_id=str(event.state.id),
            workspace_id=str(event.state.workspace_id),
            execution_id=str(event.state.execution_id),
            status=event.state.status,
        )
        logger.debug(
            "ReflectJobHandler: enqueued reflect for agent=%s task=%s status=%s",
            event.state.executing_agent_id, event.state.id, event.state.status,
        )