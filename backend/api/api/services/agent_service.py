from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.repositories.agent_repository import AgentRepository
from core.repositories.task_execution_repository import TaskExecutionRepository

if TYPE_CHECKING:
    from core.models.agents import Agent


@dataclass(frozen=True)
class CreateAgentCommand:
    """Immutable write intent — router constructs this from HTTP input; service never imports HTTP schemas."""

    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    skills: Mapping[str, float] | None
    personality: Mapping[str, Any] | None


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
    skills: Mapping[str, float] | None
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
            skills=dict(agent.skills) if agent.skills is not None else None,
            influence=agent.influence,
            created_at=agent.created_at,
        )


class AgentService:
    """Agent lifecycle boundary — accepts Commands, returns AgentData; ORM never escapes."""

    def __init__(self, repo: AgentRepository, exec_repo: TaskExecutionRepository) -> None:
        self._repo = repo
        self._exec_repo = exec_repo

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
        agents = await self._repo.list_all(workspace_id=workspace_id)
        return [AgentData.from_domain(a) for a in agents]

    async def list_active(self, workspace_id: uuid.UUID) -> list[AgentData]:
        """Active agents only — the "current agent pool" for a live dashboard.

        Matches sample_metrics.py's own definition of the agent pool (active only),
        unlike list() which returns agents of any status.
        """
        agents = await self._repo.get_all_active(workspace_id)
        return [AgentData.from_domain(a) for a in agents]

    async def delete(self, agent_id: uuid.UUID, workspace_id: uuid.UUID) -> bool:
        agent = await self._repo.get(agent_id, workspace_id)
        if agent is None:
            return False
        if await self._exec_repo.has_active_for_agent(agent_id):
            return False
        await self._repo.delete(agent)
        return True

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
