from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tenant import Workspace

if TYPE_CHECKING:
    from api.schemas.workspace import CreateWorkspaceRequest, UpdateWorkspaceRequest


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        org_id: uuid.UUID,
        body: CreateWorkspaceRequest,
    ) -> Workspace:
        ws = Workspace(
            organisation_id=org_id,
            name=body.name,
            status="active",
            config=body.config,
        )
        self._session.add(ws)
        await self._session.flush()
        return ws

    async def get(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> Workspace | None:
        ws = await self._session.get(Workspace, workspace_id)
        if ws is None or ws.organisation_id != org_id:
            return None
        return ws

    async def list(self, org_id: uuid.UUID) -> list[Workspace]:
        result = await self._session.execute(
            select(Workspace)
            .where(Workspace.organisation_id == org_id)
            .order_by(Workspace.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, ws: Workspace, body: UpdateWorkspaceRequest) -> Workspace:
        if body.name is not None:
            ws.name = body.name
        if body.status is not None:
            ws.status = body.status
        if body.result_webhook_url is not None:
            ws.result_webhook_url = body.result_webhook_url
        if body.webhook_secret is not None:
            ws.webhook_secret = body.webhook_secret
        if body.config is not None:
            ws.config = body.config
        await self._session.flush()
        return ws

    async def delete(self, ws: Workspace) -> None:
        await self._session.delete(ws)
        await self._session.flush()