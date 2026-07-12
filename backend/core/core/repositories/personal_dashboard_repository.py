from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.personal_dashboard import UserWorkspaceDashboardLayout


class PersonalDashboardRepository:
    """Postgres persistence for user-owned dashboard layout documents.

    Transaction contract: methods never commit; callers own durability.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> UserWorkspaceDashboardLayout | None:
        result = await self._session.execute(
            select(UserWorkspaceDashboardLayout).where(
                UserWorkspaceDashboardLayout.user_id == user_id,
                UserWorkspaceDashboardLayout.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID, layout: dict[str, Any], active_page: int
    ) -> UserWorkspaceDashboardLayout:
        stmt = (
            pg_insert(UserWorkspaceDashboardLayout)
            .values(
                user_id=user_id, workspace_id=workspace_id, layout=layout, active_page=active_page
            )
            .on_conflict_do_update(
                constraint="uq_user_workspace_dashboard_layout",
                set_={"layout": layout, "active_page": active_page, "updated_at": sa.func.now()},
            )
            .returning(UserWorkspaceDashboardLayout)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
