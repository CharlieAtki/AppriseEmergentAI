from __future__ import annotations

import uuid
from datetime import datetime

from core.models.tenant import Workspace
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.deps import get_workspace_observability_service, get_workspace_service, require_workspace
from api.schemas.workspace import (
    CreateWorkspaceRequest,
    EmergenceEventResponse,
    UpdateWorkspaceRequest,
    WorkspaceMetricsResponse,
    WorkspaceResponse,
)
from api.services.workspace_observability_service import WorkspaceObservabilityService
from api.services.workspace_service import (
    CreateWorkspaceCommand,
    UpdateWorkspaceCommand,
    WorkspaceService,
)

router = APIRouter()


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    request: Request,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    cmd = CreateWorkspaceCommand(
        org_id=request.state.auth.org_id,
        name=body.name,
        config=body.config,
    )
    ws = await service.create(cmd)
    return WorkspaceResponse.model_validate(ws)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    request: Request,
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[WorkspaceResponse]:
    org_id = request.state.auth.org_id
    workspaces = await service.list(org_id=org_id)
    return [WorkspaceResponse.model_validate(ws) for ws in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    request: Request,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    org_id = request.state.auth.org_id
    ws = await service.get(org_id=org_id, workspace_id=workspace_id)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return WorkspaceResponse.model_validate(ws)


@router.get("/{workspace_id}/metrics", response_model=WorkspaceMetricsResponse)
async def get_workspace_metrics(
    workspace: Workspace = Depends(require_workspace("read")),
    service: WorkspaceObservabilityService = Depends(get_workspace_observability_service),
) -> WorkspaceMetricsResponse:
    """The latest Workspace Metrics Snapshot — the routine periodic sample (Gini,
    specialisation index, agent count), distinct from an Emergence Event. See
    docs/backend/CONTEXT.md. 404 if sample_metrics hasn't run for this workspace yet
    (fewer than 2 active agents, or simply not enough time has passed)."""
    metrics = await service.get_latest_metrics(workspace.id)
    if metrics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No metrics yet")
    return WorkspaceMetricsResponse.model_validate(metrics)


@router.get("/{workspace_id}/emergence", response_model=list[EmergenceEventResponse])
async def get_workspace_emergence(
    workspace: Workspace = Depends(require_workspace("read")),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, le=200),
    service: WorkspaceObservabilityService = Depends(get_workspace_observability_service),
) -> list[EmergenceEventResponse]:
    """Recent Emergence Events (hub-detection occurrences), newest first. An
    empty list is a valid response (no hub ever detected), unlike /metrics."""
    events = await service.get_emergence_events(workspace.id, since=since, until=until, limit=limit)
    return [EmergenceEventResponse.model_validate(e) for e in events]


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    body: UpdateWorkspaceRequest,
    # workspace ORM provided by require_workspace() auth dep — passed directly to avoid a second DB read.
    # require_active=False: this route's own job includes reactivating a paused
    # workspace, so it must not be gated on the status it exists to change.
    workspace: Workspace = Depends(require_workspace("write", require_active=False)),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    cmd = UpdateWorkspaceCommand(
        name=body.name,
        status=body.status,
        result_webhook_url=body.result_webhook_url,
        webhook_secret=body.webhook_secret,
        config=body.config,
    )
    ws = await service.update(workspace, cmd)
    return WorkspaceResponse.model_validate(ws)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    # require_active=False: a paused/archived workspace must still be deletable.
    workspace: Workspace = Depends(require_workspace("write", require_active=False)),
    service: WorkspaceService = Depends(get_workspace_service),
) -> None:
    await service.delete(workspace)


# The live dashboard WebSocket (formerly GET /{workspace_id}/stream, ticket-auth'd)
# is now served directly by Centrifugo — the browser connects to Centrifugo, not
# this API process. See api/routers/centrifugo_proxy.py for the connect/subscribe
# auth callbacks Centrifugo calls back to this process for.
