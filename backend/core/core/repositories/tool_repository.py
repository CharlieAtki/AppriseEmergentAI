from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tools import Tool, WorkspaceTool


class ToolRepository:
    """Data access layer for tool catalog and workspace tool configuration.

    Transaction contract: never calls commit(). enable() flushes to populate DB-generated
    fields. All other methods never flush.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_catalog_with_workspace_status(
        self, workspace_id: uuid.UUID
    ) -> list[tuple[Tool, WorkspaceTool | None]]:
        """Return all active tools with their workspace_tools row (or None if not enabled)."""
        result = await self._session.execute(
            select(Tool, WorkspaceTool)
            .outerjoin(
                WorkspaceTool,
                (WorkspaceTool.tool_id == Tool.id) & (WorkspaceTool.workspace_id == workspace_id),
            )
            .where(Tool.is_active.is_(True))
            .order_by(Tool.category, Tool.name)
        )
        return [(tool, wt) for tool, wt in result.all()]

    async def get_tool(self, tool_id: uuid.UUID) -> Tool | None:
        return await self._session.get(Tool, tool_id)

    async def get_workspace_tool(
        self, workspace_id: uuid.UUID, tool_id: uuid.UUID
    ) -> WorkspaceTool | None:
        return await self._session.get(WorkspaceTool, (workspace_id, tool_id))

    async def enable(
        self, workspace_id: uuid.UUID, tool_id: uuid.UUID, config: dict[str, Any] | None
    ) -> WorkspaceTool:
        """Upsert the workspace_tools row. Returns the current (post-upsert) row."""
        stmt = (
            pg_insert(WorkspaceTool)
            .values(workspace_id=workspace_id, tool_id=tool_id, config=config)
            .on_conflict_do_update(
                constraint="workspace_tools_pkey",
                set_={"config": pg_insert(WorkspaceTool).excluded.config},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return await self._session.get(WorkspaceTool, (workspace_id, tool_id))  # type: ignore[return-value]

    async def disable(self, wt: WorkspaceTool) -> None:
        await self._session.delete(wt)
