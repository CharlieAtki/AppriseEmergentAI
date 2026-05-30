from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from core.coordination.task_state import TaskStateMachine
from core.database import get_session
from core.eventing.activity.base import PublishFn
from core.eventing.activity.task_logger import TaskActivityLogger
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskSnapshot, TaskUpdatedEvent
from core.models.tasks import Task, TaskExecution

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arq import ArqRedis

logger = logging.getLogger(__name__)

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "expired"})


@dataclass
class RollupSubtaskHandler(EventHandler[TaskUpdatedEvent]):
    arq_queue: ArqRedis
    publish: PublishFn

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status"):
            return
        if event.state.status not in TERMINAL_STATUSES:
            return
        if event.state.parent_task_id is None:
            return
        try:
            parent_before: TaskSnapshot | None = None
            parent_after: Task | None = None
            reflect_agent_id: uuid.UUID | None = None
            reflect_execution_id: uuid.UUID | None = None
            reflect_quality: float | None = None

            async with get_session() as session:
                parent_before, parent_after, reflect_agent_id, reflect_execution_id, reflect_quality = (
                    await self._evaluate_parent(session, event)
                )

            # Publish AFTER the session commits so downstream handlers see the
            # parent's new status in the DB, not the pre-commit state.
            if parent_before is not None and parent_after is not None:
                task_logger = TaskActivityLogger(self.publish)
                await task_logger.updated(parent_before, parent_after)

            if reflect_agent_id is not None and reflect_execution_id is not None and reflect_quality is not None:
                await self.arq_queue.enqueue_job(
                    "reflect",
                    agent_id=str(reflect_agent_id),
                    task_id=str(event.state.parent_task_id),
                    workspace_id=str(event.state.workspace_id),
                    execution_id=str(reflect_execution_id),
                    quality_score=reflect_quality,
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
    ) -> tuple[TaskSnapshot | None, Task | None, uuid.UUID | None, uuid.UUID | None, float | None]:
        """Promote the parent task if all siblings have reached a terminal state.

        Returns (before_snapshot, parent_task, reflect_agent_id, execution_id, avg_quality)
        when rollup occurs, or (None, None, None, None, None) when it does not.

        execution_id and avg_quality are needed to enqueue a reflect job for the
        coordinator agent. execution_id is the parent's decompose execution (the only
        execution the coordinator ran). avg_quality is the mean quality score across
        completed sibling executions — the same signal used by AgentCreditHandler to
        credit the coordinator's influence.

        Both are None when all siblings failed (no quality signal available) or when no
        decompose execution exists for the parent, in which case the caller skips the
        reflect enqueue.

        The caller publishes the parent event and enqueues reflect after the session
        commits so downstream handlers see the committed DB state.
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
            return None, None, None, None, None
        if not {s.status for s in siblings}.issubset(TERMINAL_STATUSES):
            return None, None, None, None, None

        parent = await session.get(Task, parent_id)
        if parent is None or parent.status in TERMINAL_STATUSES:
            return None, None, None, None, None  # already resolved — concurrent rollup guard

        before = TaskSnapshot.from_domain(parent)
        any_failed = any(s.status == "failed" for s in siblings)
        TaskStateMachine.transition(parent, "failed" if any_failed else "completed")

        # Avg quality from completed siblings — mirrors AgentCreditHandler coordinator credit.
        completed_ids = [s.id for s in siblings if s.status == "completed"]
        avg_quality: float | None = None
        if completed_ids:
            avg_quality = (await session.execute(
                select(func.avg(TaskExecution.quality_score)).where(
                    TaskExecution.task_id.in_(completed_ids),
                    TaskExecution.status == "completed",
                )
            )).scalar()

        # Parent's decompose execution — the coordinator's execution record for reflect.
        execution_id: uuid.UUID | None = (await session.execute(
            select(TaskExecution.id).where(
                TaskExecution.task_id == parent_id,
                TaskExecution.execution_path == "decompose",
            ).limit(1)
        )).scalar()

        reflect_agent = parent.coordinator_agent_id or parent.created_by_agent_id
        return before, parent, reflect_agent, execution_id, avg_quality
