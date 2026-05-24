from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import func, select

from core.coordination.influence import compute_influence_ema
from core.database import get_session
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskUpdatedEvent
from core.models.agents import Agent
from core.models.observability import InfluenceSnapshot
from core.models.tasks import Task, TaskExecution

logger = logging.getLogger(__name__)


@dataclass
class CoordinatorInfluenceHandler(EventHandler[TaskUpdatedEvent]):
    """Credits the coordinator agent's influence when a delegated task completes.

    Fires whenever a task with coordinator_agent_id transitions to "completed".
    The coordinator is the agent that decomposed the task; its influence is updated
    using the average quality score of the completed subtasks, rewarding effective
    delegation.

    Runs fire-and-forget after RollupSubtaskHandler publishes the parent's
    TaskUpdatedEvent. Non-atomic with the parent status commit — one missed update
    has negligible effect on the coordinator's EMA. SoC wins over strict atomicity.

    Race condition: same as InfluenceUpdateHandler — concurrent completions across
    workers may overwrite each other. Accepted for Phase 1.
    """

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status") or event.state.status != "completed":
            return
        if event.state.coordinator_agent_id is None:
            return

        async with get_session() as session:
            completed_subtask_ids = (await session.execute(
                select(Task.id).where(
                    Task.parent_task_id == event.state.id,
                    Task.workspace_id == event.state.workspace_id,
                    Task.status == "completed",
                )
            )).scalars().all()

            if not completed_subtask_ids:
                return

            avg_quality: float = (await session.execute(
                select(func.avg(TaskExecution.quality_score)).where(
                    TaskExecution.task_id.in_(completed_subtask_ids),
                    TaskExecution.status == "completed",
                )
            )).scalar() or 0.0

            coordinator = await session.get(Agent, event.state.coordinator_agent_id)
            if coordinator is None:
                return

            coordinator.influence = compute_influence_ema(coordinator.influence, avg_quality)
            session.add(coordinator)
            session.add(InfluenceSnapshot(
                agent_id=coordinator.id,
                organisation_id=coordinator.organisation_id,
                workspace_id=coordinator.workspace_id,
                influence=coordinator.influence,
            ))

        logger.debug(
            "CoordinatorInfluenceHandler: agent=%s influence=%.4f",
            event.state.coordinator_agent_id, coordinator.influence,
        )
