from __future__ import annotations

from typing import TYPE_CHECKING

from core.activity.base import ActivityLogger
from core.events.agent_events import AgentCreatedEvent, AgentDeletedEvent, AgentSnapshot, AgentUpdatedEvent

if TYPE_CHECKING:
    from core.models.agents import Agent


class AgentActivityLogger(ActivityLogger):
    async def agent_created(self, agent: Agent) -> None:
        snapshot = AgentSnapshot.from_domain(agent)
        await self._publish(AgentCreatedEvent(state=snapshot, workspace_id=agent.workspace_id))

    async def agent_updated(self, before: Agent, after: Agent) -> None:
        await self._publish(
            AgentUpdatedEvent(
                state=AgentSnapshot.from_domain(after),
                before=AgentSnapshot.from_domain(before),
                workspace_id=after.workspace_id,
            )
        )

    async def agent_deleted(self, agent: Agent) -> None:
        snapshot = AgentSnapshot.from_domain(agent)
        await self._publish(AgentDeletedEvent(state=snapshot, workspace_id=agent.workspace_id))
