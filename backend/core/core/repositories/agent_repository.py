from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models.agents import Agent


class AgentRepository:
    """Concrete AgentRepository backed by SQLAlchemy AsyncSession.

    Same construction and transaction contract as TaskRepository — never commits,
    never flushes internally except create() (which flushes to populate agent.id).

    API paths: use get(agent_id, workspace_id) — workspace ownership enforced in SQL.
    Worker paths: use get_by_id(agent_id) — caller already owns the ID by construction.
    Never use get_by_id() in API routers.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        workspace_id: uuid.UUID,
        organisation_id: uuid.UUID,
        name: str,
        skills: dict[str, Any] | None,
        personality: dict[str, Any] | None,
    ) -> Agent:
        """Create and stage a new Agent, flushing to populate agent.id before returning.

        Flushes internally so the caller immediately has a populated id. Does not commit;
        caller owns the transaction boundary.
        """
        agent = Agent(
            workspace_id=workspace_id,
            organisation_id=organisation_id,
            name=name,
            status="active",
            skills=skills,
            personality=personality,
        )
        self._session.add(agent)
        await self._session.flush()
        return agent

    async def get(self, agent_id: uuid.UUID, workspace_id: uuid.UUID) -> Agent | None:
        """Fetch an Agent by PK with mandatory workspace ownership filter.

        Workspace filter is enforced in SQL. Use this in all API router paths.
        For internal worker paths, use get_by_id().
        """
        result = await self._session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, agent_id: uuid.UUID) -> Agent | None:
        """Fetch an Agent by PK with no workspace filter.

        Unscoped by design — for internal worker paths that already own the agent ID
        by construction (job arguments, event payloads). Never call this from API routers.
        """
        return await self._session.get(Agent, agent_id)

    async def get_for_execution(self, agent_id: uuid.UUID) -> Agent | None:
        """Fetch an Agent with the relationships needed by execute_task (task_executions).

        Named for the use case — callers should not need to know which relationships
        are loaded. If execute_task's needs change, update this method, not the callers.
        """
        return await self._session.get(
            Agent, agent_id, options=[selectinload(Agent.task_executions)]
        )

    async def get_for_update(self, agent_id: uuid.UUID) -> Agent | None:
        """Fetch an Agent with a row-level lock (SELECT ... FOR UPDATE).

        Used by _stage_skills in the reflect pipeline to prevent concurrent skill
        overwrites between reflection and execute_task's skill decay.
        """
        return await self._session.get(Agent, agent_id, with_for_update=True)

    async def get_active_for_bidding(
        self,
        workspace_id: uuid.UUID,
        exclude_id: uuid.UUID | None = None,
    ) -> list[Agent]:
        """Fetch active agents with task_executions loaded for bid scoring.

        exclude_id omits one agent — used by the CFP path to exclude the initiating
        agent from its own call-for-proposals round.
        """
        conditions = [Agent.workspace_id == workspace_id, Agent.status == "active"]
        if exclude_id is not None:
            conditions.append(Agent.id != exclude_id)
        result = await self._session.execute(
            select(Agent).where(*conditions).options(selectinload(Agent.task_executions))
        )
        return list(result.scalars().all())

    async def get_all_active(
        self,
        workspace_id: uuid.UUID,
        exclude_id: uuid.UUID | None = None,
    ) -> list[Agent]:
        """Fetch active agents with no eager loading.

        exclude_id omits one agent — used by social_memory to exclude the completing agent
        from peer observation writes.
        """
        conditions = [Agent.workspace_id == workspace_id, Agent.status == "active"]
        if exclude_id is not None:
            conditions.append(Agent.id != exclude_id)
        result = await self._session.execute(select(Agent).where(*conditions))
        return list(result.scalars().all())

    async def list_all(self, workspace_id: uuid.UUID) -> list[Agent]:
        result = await self._session.execute(
            select(Agent)
            .where(Agent.workspace_id == workspace_id)
            .order_by(Agent.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_fields(
        self,
        agent: Agent,
        *,
        name: str | None = None,
        status: str | None = None,
    ) -> Agent:
        """Mutate agent fields in-place and stage the agent.

        Does not flush or commit — caller is responsible for the transaction boundary.
        """
        if name is not None:
            agent.name = name
        if status is not None:
            agent.status = status
        self._session.add(agent)
        return agent

    async def save(self, agent: Agent) -> None:
        """Stage agent for persistence via session.add().

        async for interface consistency — session.add() is not I/O and does not block
        the event loop. Caller is responsible for flush/commit.
        """
        self._session.add(agent)
