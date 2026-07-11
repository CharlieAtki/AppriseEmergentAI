from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.observability import InfluenceSnapshot


class InfluenceSnapshotRepository:
    """Concrete read repository for InfluenceSnapshot history.

    Distinct from InfluenceRepository (core/repositories/influence_repository.py),
    which is the write-only path AgentCreditHandler uses to record snapshots on
    task completion — this is a new read path and must not be merged into that
    class, per the same explicit-boundary instinct as service DTOs.

    Transaction contract: never calls commit() — matches WorkspaceMetricsRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_agents(
        self,
        workspace_id: uuid.UUID,
        agent_ids: Sequence[uuid.UUID],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit_per_agent: int | None = None,
    ) -> list[InfluenceSnapshot]:
        """Per-agent influence history, ascending by recorded_at within each agent.

        Calendar mode (since/until) and last-N mode (limit_per_agent) are mutually
        exclusive query shapes — InfluenceSnapshot writes are event-driven (on
        task.completed), not scheduled, so a calendar window can return 0-1 rows
        for a low-activity agent; limit_per_agent is the fallback callers use to
        still get a meaningful series for those agents.
        """
        if not agent_ids:
            return []

        if limit_per_agent is not None:
            ranked_ids = (
                select(
                    InfluenceSnapshot.id,
                    func.row_number()
                    .over(
                        partition_by=InfluenceSnapshot.agent_id,
                        order_by=InfluenceSnapshot.recorded_at.desc(),
                    )
                    .label("rank"),
                )
                .where(
                    InfluenceSnapshot.workspace_id == workspace_id,
                    InfluenceSnapshot.agent_id.in_(agent_ids),
                )
                .subquery()
            )
            query = (
                select(InfluenceSnapshot)
                .join(ranked_ids, InfluenceSnapshot.id == ranked_ids.c.id)
                .where(ranked_ids.c.rank <= limit_per_agent)
                .order_by(InfluenceSnapshot.agent_id, InfluenceSnapshot.recorded_at.asc())
            )
            result = await self._session.execute(query)
            return list(result.scalars().all())

        query = select(InfluenceSnapshot).where(
            InfluenceSnapshot.workspace_id == workspace_id,
            InfluenceSnapshot.agent_id.in_(agent_ids),
        )
        if since is not None:
            query = query.where(InfluenceSnapshot.recorded_at >= since)
        if until is not None:
            query = query.where(InfluenceSnapshot.recorded_at <= until)
        query = query.order_by(InfluenceSnapshot.agent_id, InfluenceSnapshot.recorded_at.asc())
        result = await self._session.execute(query)
        return list(result.scalars().all())
