from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tenant import Workspace


class WorkspaceRepository:
    """Concrete WorkspaceRepository backed by SQLAlchemy AsyncSession.

    API paths: use get(org_id, workspace_id) — org ownership enforced in SQL.
    Worker paths: use get_by_id(workspace_id) — caller already owns the ID by construction.
    Cross-workspace admin queries (cron jobs) belong on WorkspaceAdminRepository (deferred
    until the cron job layer is refactored). Importing WorkspaceAdminRepository is a
    privilege signal — any file that does so touches all workspaces.

    Transaction contract: never calls commit(). create() flushes to populate the
    DB-generated id before returning. All other methods never flush.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, org_id: uuid.UUID, name: str, config: dict[str, Any] | None
    ) -> Workspace:
        """Stage and flush — caller needs ws.id immediately for the HTTP response."""
        ws = Workspace(organisation_id=org_id, name=name, status="active", config=config)
        self._session.add(ws)
        await self._session.flush()
        return ws

    async def get(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> Workspace | None:
        """Org-scoped lookup — enforces tenant ownership in SQL. Use in all API paths."""
        result = await self._session.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.organisation_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None:
        """Unscoped PK lookup — for internal worker paths only (e.g. deliver_webhook).
        Never call this from API routers — use get() instead."""
        return await self._session.get(Workspace, workspace_id)

    async def list(self, org_id: uuid.UUID) -> list[Workspace]:
        result = await self._session.execute(
            select(Workspace)
            .where(Workspace.organisation_id == org_id)
            .order_by(Workspace.created_at.desc())
        )
        return list(result.scalars().all())

    async def save(self, ws: Workspace) -> None:
        """Re-stage after field mutations (update path). No flush — session commits on exit."""
        self._session.add(ws)

    async def delete(self, ws: Workspace) -> None:
        """Stage for deletion. No flush — session commits on exit."""
        await self._session.delete(ws)
