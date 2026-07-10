from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.observability import WorkspaceMetricsSnapshot


class WorkspaceMetricsRepository:
    """Concrete WorkspaceMetricsRepository backed by SQLAlchemy AsyncSession.

    Transaction contract: never calls commit() — matches WorkspaceRepository/AgentRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest(self, workspace_id: uuid.UUID) -> WorkspaceMetricsSnapshot | None:
        """Most recent snapshot for a workspace, or None if sample_metrics hasn't run yet."""
        result = await self._session.execute(
            select(WorkspaceMetricsSnapshot)
            .where(WorkspaceMetricsSnapshot.workspace_id == workspace_id)
            .order_by(WorkspaceMetricsSnapshot.recorded_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
