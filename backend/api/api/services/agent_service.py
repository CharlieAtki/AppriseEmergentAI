from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from core.models.agents import Agent
from core.models.tenant import Workspace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from api.schemas.agent import CreateAgentRequest, UpdateAgentRequest


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, workspace: Workspace, body: CreateAgentRequest) -> Agent:
        agent = Agent(
            workspace_id=workspace.id,
            organisation_id=workspace.organisation_id,
            name=body.name,
            status="active",
            skills=body.skills,
            personality=body.personality,
        )
        self._session.add(agent)
        await self._session.flush()
        return agent

    async def get(self, workspace_id: uuid.UUID, agent_id: uuid.UUID) -> Agent | None:
        agent = await self._session.get(Agent, agent_id)
        if agent is None or agent.workspace_id != workspace_id:
            return None
        return agent

    async def list(self, workspace_id: uuid.UUID) -> list[Agent]:
        result = await self._session.execute(
            select(Agent)
            .where(Agent.workspace_id == workspace_id)
            .order_by(Agent.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, agent: Agent, body: UpdateAgentRequest) -> Agent:
        if body.name is not None:
            agent.name = body.name
        if body.status is not None:
            agent.status = body.status
        await self._session.flush()
        return agent
