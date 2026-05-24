from __future__ import annotations

import logging
from dataclasses import dataclass

from core.coordination.influence import compute_influence_ema
from core.database import get_session
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskUpdatedEvent
from core.models.agents import Agent
from core.models.observability import InfluenceSnapshot

logger = logging.getLogger(__name__)


@dataclass
class InfluenceUpdateHandler(EventHandler[TaskUpdatedEvent]):
    """Updates the executing agent's influence score via EMA when a self-execute task completes.

    Influence is a soft exponential moving average of task quality scores. It
    reflects an agent's sustained performance over time and feeds directly into
    ContractNet bid scoring — higher influence makes an agent more competitive
    for future tasks in the workspace.

    Runs fire-and-forget after the Phase 6 atomic commit in execute_task. This
    means task completion and the influence update are no longer atomic: if this
    handler fails or the worker crashes between the commit and handler execution,
    the influence update for that task is lost. This is an accepted trade-off —
    influence is a soft EMA score and one missed update has negligible effect on
    an agent's long-running average. SoC wins over strict atomicity here.

    Race condition note: if two tasks for the same agent complete simultaneously
    across multiple ARQ workers, two handler instances may read the same influence
    value and overwrite each other. Accepted for Phase 1. Phase 2 can introduce a
    compare-and-swap or advisory lock if this becomes a concern at scale.
    """

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status") or event.state.status != "completed":
            return
        if event.state.execution_path != "self_execute":
            return
        if event.state.executing_agent_id is None or event.state.quality_score is None:
            return

        async with get_session() as session:
            agent = await session.get(Agent, event.state.executing_agent_id)
            if agent is None:
                return

            agent.influence = compute_influence_ema(agent.influence, event.state.quality_score)
            session.add(agent)
            session.add(InfluenceSnapshot(
                agent_id=agent.id,
                organisation_id=agent.organisation_id,
                workspace_id=agent.workspace_id,
                influence=agent.influence,
            ))

        logger.debug(
            "InfluenceUpdateHandler: agent=%s influence=%.4f",
            event.state.executing_agent_id, agent.influence,
        )
