from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.observability import SkillSnapshot


class SkillRepository:
    """Concrete SkillRepository backed by SQLAlchemy AsyncSession.

    SkillSnapshot is a write-once audit record — one row per task execution.
    The unique partial index on execution_id is the DB backstop for idempotency;
    get_by_execution() is the application-level guard called before record().

    Transaction contract: never calls commit(). All methods stage changes;
    the caller owns the transaction boundary via span.session().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_execution(
        self, execution_id: uuid.UUID, agent_id: uuid.UUID
    ) -> SkillSnapshot | None:
        """Idempotency check — returns existing snapshot for this execution if present.

        Both execution_id and agent_id are included in the filter to make the
        intent explicit, even though execution_id alone satisfies the DB constraint.
        """
        return await self._session.scalar(
            select(SkillSnapshot).where(
                SkillSnapshot.execution_id == execution_id,
                SkillSnapshot.agent_id == agent_id,
            )
        )

    async def record(
        self,
        agent_id: uuid.UUID,
        organisation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        skills: Mapping[str, float],
        execution_id: uuid.UUID,
    ) -> None:
        """Stage a SkillSnapshot for the audit trail. Does not flush or commit."""
        self._session.add(
            SkillSnapshot(
                agent_id=agent_id,
                organisation_id=organisation_id,
                workspace_id=workspace_id,
                skills=dict(skills),
                execution_id=execution_id,
            )
        )
