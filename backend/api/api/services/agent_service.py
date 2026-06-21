from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.repositories.agent_repository import AgentRepository

if TYPE_CHECKING:
    from core.models.agents import Agent


@dataclass(frozen=True)
class CreateAgentCommand:
    """Immutable write intent — router constructs this from HTTP input; service never imports HTTP schemas."""

    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    skills: dict[str, float] | None
    personality: dict[str, Any] | None


@dataclass(frozen=True)
class UpdateAgentCommand:
    """Partial update intent — None fields are skipped; only supplied fields are written."""

    name: str | None
    status: str | None


@dataclass(frozen=True)
class AgentData:
    """ORM boundary DTO — the Agent ORM model never leaves the service layer; callers hold this instead."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    status: str
    skills: dict[str, float] | None
    influence: float | None
    created_at: datetime

    @classmethod
    def from_domain(cls, agent: Agent) -> AgentData:
        # Explicit field mapping — mirrors TaskContext.from_task(); no hidden ORM introspection.
        return cls(
            id=agent.id,
            workspace_id=agent.workspace_id,
            name=agent.name,
            status=agent.status,
            skills=agent.skills,
            influence=agent.influence,
            created_at=agent.created_at,
        )


class AgentService:
    """Agent lifecycle boundary — accepts Commands, returns AgentData; ORM never escapes."""

    def __init__(self, repo: AgentRepository) -> None:
        self._repo = repo

    async def create(self, cmd: CreateAgentCommand) -> AgentData:
        agent = await self._repo.create(
            workspace_id=cmd.workspace_id,
            organisation_id=cmd.organisation_id,
            name=cmd.name,
            skills=cmd.skills,
            personality=cmd.personality,
        )
        return AgentData.from_domain(agent)

    async def get(self, agent_id: uuid.UUID, workspace_id: uuid.UUID) -> AgentData | None:
        agent = await self._repo.get(agent_id, workspace_id)
        return AgentData.from_domain(agent) if agent is not None else None

    async def list(self, workspace_id: uuid.UUID) -> list[AgentData]:
        agents = await self._repo.list(workspace_id=workspace_id)
        return [AgentData.from_domain(a) for a in agents]

    async def update(
        self,
        agent_id: uuid.UUID,
        workspace_id: uuid.UUID,
        cmd: UpdateAgentCommand,
    ) -> AgentData | None:
        # Returns None so the router decides the HTTP status code; no 404 raised here.
        agent = await self._repo.get(agent_id, workspace_id)
        if agent is None:
            return None
        agent = await self._repo.update_fields(agent, name=cmd.name, status=cmd.status)
        return AgentData.from_domain(agent)
