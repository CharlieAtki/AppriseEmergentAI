from __future__ import annotations

import uuid
from collections.abc import Mapping
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
    config: Mapping[str, Any] | None


@dataclass(frozen=True)
class UpdateWorkspaceCommand:
    """Partial update intent — None fields are skipped; webhook_secret accepted here but excluded from WorkspaceData."""

    name: str | None
    status: str | None
    result_webhook_url: str | None
    webhook_secret: str | None
    config: Mapping[str, Any] | None


@dataclass(frozen=True)
class WorkspaceData:
    """ORM boundary DTO — webhook_secret absent; it is an HMAC key and must never appear in API responses."""

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    status: str
    result_webhook_url: str | None
    created_at: datetime | None
    agent_count: int = 0

    @classmethod
    def from_domain(cls, ws: Workspace, *, agent_count: int = 0) -> WorkspaceData:
        # Explicit field mapping — no introspection; webhook_secret intentionally omitted.
        return cls(
            id=ws.id,
            organisation_id=ws.organisation_id,
            name=ws.name,
            status=ws.status,
            result_webhook_url=ws.result_webhook_url,
            created_at=ws.created_at,
            agent_count=agent_count,
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

    async def get_active(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> WorkspaceData | None:
        """Ownership + active-status check in one call — returns None if the org
        doesn't own the workspace or it's not active. Used by callers that only
        need an allow/deny decision (e.g. the Centrifugo subscribe proxy), not a
        distinct 404-vs-409 HTTP response — require_workspace() in deps.py keeps
        its own two-step check for that distinction, but both call
        Workspace.is_active_status() as the single source of truth for what
        "active" means, so the invariant itself is never duplicated."""
        ws = await self._repo.get(org_id=org_id, workspace_id=workspace_id)
        if ws is None or not Workspace.is_active_status(ws.status):
            return None
        return WorkspaceData.from_domain(ws)

    async def list(self, org_id: uuid.UUID) -> list[WorkspaceData]:
        rows = await self._repo.list_with_agent_counts(org_id=org_id)
        return [WorkspaceData.from_domain(ws, agent_count=count) for ws, count in rows]

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
