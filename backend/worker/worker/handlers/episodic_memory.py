from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select

from core.database import get_session
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskUpdatedEvent
from core.memory.agent_memory import AgentMemory
from core.models.tasks import TaskExecution

logger = logging.getLogger(__name__)


@dataclass
class EpisodicMemoryHandler(EventHandler[TaskUpdatedEvent]):
    """Writes an episodic memory entry for the executing agent when a task completes.

    Episodic memory records what this specific agent did — the task it worked on,
    its type, and the quality of the outcome. Distinct from social memory, which
    records observations about peer agents across the workspace.

    Only fires for the self-execute path. Decompose and CFP executions produce a
    completed execution row with no quality_score — the task was delegated, not
    actually worked on — so no episode is written for those paths.

    The handler queries TaskExecution to get quality_score. This is one extra DB
    read per completion but runs fire-and-forget so it does not block execute_task.

    Phase 2 extension point: when ArtifactContribution records exist, this handler
    can be updated to include content_ref and operation_type in the episode payload.
    execute_task does not need to change — the handler queries the artifact tables
    independently.
    """

    memory: AgentMemory

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

        await self.memory.store_episode(
            str(event.state.executing_agent_id),
            str(event.state.workspace_id),
            {
                "text":          f"Completed task: {event.state.title}. Quality: {execution.quality_score:.2f}.",
                "task_id":       str(event.state.id),
                "task_type":     event.state.task_type,
                "quality_score": execution.quality_score,
            },
        )
        logger.debug(
            "EpisodicMemoryHandler: wrote episode for agent=%s task=%s quality=%.3f",
            event.state.executing_agent_id, event.state.id, execution.quality_score,
        )
