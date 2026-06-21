from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.models.observability import InfluenceSnapshot


class InfluenceRepository:
    """Concrete InfluenceRepository backed by SQLAlchemy AsyncSession.

    InfluenceSnapshot is a write-only audit record — no idempotency guard needed
    because multiple snapshots per task completion are expected (executor + coordinators).
    Each call to record() adds a new row to the audit trail.

    Transaction contract: never calls commit(). record() stages the snapshot;
    the caller owns the transaction boundary via get_session().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        agent_id: uuid.UUID,
        organisation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        influence: float,
    ) -> None:
        """Stage an InfluenceSnapshot for the audit trail. Does not flush or commit."""
        self._session.add(
            InfluenceSnapshot(
                agent_id=agent_id,
                organisation_id=organisation_id,
                workspace_id=workspace_id,
                influence=influence,
            )
        )
