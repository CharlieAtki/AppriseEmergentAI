from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.tenant import Workspace
from core.repositories.workspace_repository import WorkspaceRepository

if TYPE_CHECKING:
    import uuid

    from api.schemas.workspace import CreateWorkspaceRequest, UpdateWorkspaceRequest


class WorkspaceService:
    def __init__(self, repo: WorkspaceRepository) -> None:
        self._repo = repo

    async def create(
        self,
        org_id: uuid.UUID,
        body: CreateWorkspaceRequest,
    ) -> Workspace:
        return await self._repo.create(org_id=org_id, name=body.name, config=body.config)

    async def get(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> Workspace | None:
        return await self._repo.get(org_id=org_id, workspace_id=workspace_id)

    async def list(self, org_id: uuid.UUID) -> list[Workspace]:
        return await self._repo.list(org_id=org_id)

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
        await self._repo.save(ws)
        return ws

    async def delete(self, ws: Workspace) -> None:
        await self._repo.delete(ws)
