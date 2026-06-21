from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.models.tenant import Workspace
from core.repositories.workspace_repository import WorkspaceRepository


@dataclass(frozen=True)
class CreateWorkspaceCommand:
    """Immutable write intent — router constructs this from HTTP input; service never imports HTTP schemas."""

    org_id: uuid.UUID
    name: str
    config: dict[str, Any] | None


@dataclass(frozen=True)
class UpdateWorkspaceCommand:
    """Partial update intent — None fields are skipped; webhook_secret accepted here but excluded from WorkspaceData."""

    name: str | None
    status: str | None
    result_webhook_url: str | None
    webhook_secret: str | None
    config: dict[str, Any] | None


@dataclass(frozen=True)
class WorkspaceData:
    """ORM boundary DTO — webhook_secret absent; it is an HMAC key and must never appear in API responses."""

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    status: str
    result_webhook_url: str | None
    created_at: datetime | None

    @classmethod
    def from_domain(cls, ws: Workspace) -> WorkspaceData:
        # Explicit field mapping — no introspection; webhook_secret intentionally omitted.
        return cls(
            id=ws.id,
            organisation_id=ws.organisation_id,
            name=ws.name,
            status=ws.status,
            result_webhook_url=ws.result_webhook_url,
            created_at=ws.created_at,
        )


class WorkspaceService:
    """Workspace lifecycle boundary — accepts Commands, returns WorkspaceData; ORM never escapes."""

    def __init__(self, repo: WorkspaceRepository) -> None:
        self._repo = repo

    async def create(self, cmd: CreateWorkspaceCommand) -> WorkspaceData:
        ws = await self._repo.create(org_id=cmd.org_id, name=cmd.name, config=cmd.config)
        return WorkspaceData.from_domain(ws)

    async def get(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> WorkspaceData | None:
        ws = await self._repo.get(org_id=org_id, workspace_id=workspace_id)
        return WorkspaceData.from_domain(ws) if ws is not None else None

    async def list(self, org_id: uuid.UUID) -> list[WorkspaceData]:
        workspaces = await self._repo.list_all(org_id=org_id)
        return [WorkspaceData.from_domain(ws) for ws in workspaces]

    async def update(self, ws: Workspace, cmd: UpdateWorkspaceCommand) -> WorkspaceData:
        # ws loaded by require_workspace() auth dep — accept ORM directly to avoid a second DB read.
        if cmd.name is not None:
            ws.name = cmd.name
        if cmd.status is not None:
            ws.status = cmd.status
        if cmd.result_webhook_url is not None:
            ws.result_webhook_url = cmd.result_webhook_url
        if cmd.webhook_secret is not None:
            ws.webhook_secret = cmd.webhook_secret
        if cmd.config is not None:
            ws.config = cmd.config
        await self._repo.save(ws)
        return WorkspaceData.from_domain(ws)

    async def delete(self, ws: Workspace) -> None:
        await self._repo.delete(ws)
