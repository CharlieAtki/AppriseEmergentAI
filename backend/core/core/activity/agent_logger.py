"""Activity-logger facade for agent domain events.

:class:`AgentActivityLogger` constructs the appropriate event payload from a
SQLAlchemy model and forwards it through ``publish``. It knows nothing about
handlers, the bus, or dispatch — its only job is translating a domain action
into a correctly shaped event.

Logger methods read scalar attributes from their argument. This works even on
detached SQLAlchemy instances, since SQLAlchemy keeps cached scalar values in
``__dict__`` after detach.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from core.activity.base import PublishFn
from core.events.agent_events import AgentCreatedEvent, AgentDeletedEvent, AgentSnapshot, AgentUpdatedEvent

if TYPE_CHECKING:
    from core.models.agents import Agent


class AgentActivityLogger:
    """Endpoint-side facade that constructs agent lifecycle events and publishes them after commit."""

    def __init__(self, publish: PublishFn) -> None:
        self._publish = publish

    async def created(self, agent: Agent) -> None:
        snapshot = AgentSnapshot.from_domain(agent)
        await self._publish(AgentCreatedEvent(state=snapshot, workspace_id=agent.workspace_id))

    async def updated(self, before: AgentSnapshot, after: Agent) -> None:
        await self._publish(
            AgentUpdatedEvent(
                state=AgentSnapshot.from_domain(after),
                before=before,
                workspace_id=after.workspace_id,
            )
        )

    async def deleted(self, agent: Agent) -> None:
        snapshot = AgentSnapshot.from_domain(agent)
        await self._publish(AgentDeletedEvent(state=snapshot, workspace_id=agent.workspace_id))