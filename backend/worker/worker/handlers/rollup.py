from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from core.eventing.bus.handlers import EventHandler
from core.coordination.task_state import TaskStateMachine
from core.database import get_session
from core.eventing.events.task_events import TaskUpdatedEvent
from core.models.tasks import Task

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arq import ArqRedis

logger = logging.getLogger(__name__)

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "expired"})


@dataclass
class RollupSubtaskHandler(EventHandler[TaskUpdatedEvent]):
    arq_queue: ArqRedis

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status"):
            return
        if event.state.status not in TERMINAL_STATUSES:
            return
        if event.state.parent_task_id is None:
            return
        try:
            async with get_session() as session:
                reflect_agent_id = await self._evaluate_parent(session, event)
            # Enqueue AFTER the session commits — the reflect job must see the
            # parent's new status in the DB, not the pre-commit state.
            if reflect_agent_id is not None:
                await self.arq_queue.enqueue_job(
                    "reflect",
                    agent_id=str(reflect_agent_id),
                    task_id=str(event.state.parent_task_id),
                    workspace_id=str(event.state.workspace_id),
                )
        except Exception:
            logger.exception(
                "RollupSubtaskHandler failed for task=%s parent=%s",
                event.state.id,
                event.state.parent_task_id,
            )

    async def _evaluate_parent(
        self,
        session: AsyncSession,
        event: TaskUpdatedEvent,
    ) -> uuid.UUID | None:
        """Evaluate whether the parent task can be completed.

        Returns the agent ID to enqueue a reflect job for, or None if no
        rollup occurred. The caller enqueues after the session commits.
        """
        parent_id = event.state.parent_task_id
        workspace_id = event.state.workspace_id

        siblings = (await session.execute(
            select(Task).where(
                Task.parent_task_id == parent_id,
                Task.workspace_id == workspace_id,
            )
        )).scalars().all()

        if not siblings:
            return None
        if not {s.status for s in siblings}.issubset(TERMINAL_STATUSES):
            return None

        parent = await session.get(Task, parent_id)
        if parent is None or parent.status in TERMINAL_STATUSES:
            return None  # already resolved — concurrent rollup guard

        any_failed = any(s.status == "failed" for s in siblings)
        TaskStateMachine.transition(parent, "failed" if any_failed else "completed")

        if not any_failed and parent.coordinator_agent_id is not None:
            await self._credit_coordinator(session, parent, siblings)

        return parent.coordinator_agent_id or parent.created_by_agent_id

    async def _credit_coordinator(
        self,
        session: AsyncSession,
        parent: Task,
        siblings: list[Task],
    ) -> None:
        from core.config import settings
        from core.models.agents import Agent
        from core.models.observability import InfluenceSnapshot
        from core.models.tasks import TaskExecution

        coordinator = await session.get(Agent, parent.coordinator_agent_id)
        if coordinator is None:
            return

        completed_ids = [s.id for s in siblings if s.status == "completed"]
        if not completed_ids:
            return

        avg_quality: float = (await session.execute(
            select(func.avg(TaskExecution.quality_score)).where(
                TaskExecution.task_id.in_(completed_ids),
                TaskExecution.status == "completed",
            )
        )).scalar() or 0.0

        base = coordinator.influence if coordinator.influence is not None else 0.0
        coordinator.influence = base + settings.INFLUENCE_EMA_ALPHA * (avg_quality - base)

        session.add(InfluenceSnapshot(
            agent_id=coordinator.id,
            organisation_id=coordinator.organisation_id,
            workspace_id=coordinator.workspace_id,
            influence=coordinator.influence,
        ))
