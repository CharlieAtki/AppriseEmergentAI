from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tenant import Workspace


class WorkspaceRepository:
    """Concrete WorkspaceRepository backed by SQLAlchemy AsyncSession.

    Single-workspace PK lookup only. Cross-workspace admin queries (e.g. listing
    all active workspaces for cron jobs) belong on WorkspaceAdminRepository, which
    is deferred until the cron job layer is refactored. Importing WorkspaceAdminRepository
    is a privilege signal — any file that does so touches all workspaces.

    Transaction contract: never calls commit() or flush(). Callers own the transaction
    boundary via span.session() or get_session() context managers.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None:
        """Unscoped PK lookup — for internal worker paths only (e.g. deliver_webhook).
        Never call this from API routers — use a workspace-scoped query instead."""
        return await self._session.get(Workspace, workspace_id)
