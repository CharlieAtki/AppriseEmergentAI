from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.observability import EmergenceEvent


class EmergenceEventRepository:
    """Concrete EmergenceEventRepository backed by SQLAlchemy AsyncSession.

    Transaction contract: never calls commit() — matches WorkspaceMetricsRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_recent(
        self,
        workspace_id: uuid.UUID,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> list[EmergenceEvent]:
        """Newest-first EmergenceEvents for a workspace, uses the existing
        (workspace_id, recorded_at) index."""
        query = select(EmergenceEvent).where(EmergenceEvent.workspace_id == workspace_id)
        if since is not None:
            query = query.where(EmergenceEvent.recorded_at >= since)
        if until is not None:
            query = query.where(EmergenceEvent.recorded_at <= until)
        query = query.order_by(EmergenceEvent.recorded_at.desc()).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())
