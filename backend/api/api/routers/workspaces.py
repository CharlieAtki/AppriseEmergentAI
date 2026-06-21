from __future__ import annotations

import uuid

from core.models.tenant import Workspace
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.deps import get_workspace_service, require_workspace
from api.schemas.workspace import CreateWorkspaceRequest, UpdateWorkspaceRequest, WorkspaceResponse
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


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    body: UpdateWorkspaceRequest,
    # workspace ORM provided by require_workspace() auth dep — passed directly to avoid a second DB read.
    workspace: Workspace = Depends(require_workspace("write")),
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
    workspace: Workspace = Depends(require_workspace("write")),
    service: WorkspaceService = Depends(get_workspace_service),
) -> None:
    await service.delete(workspace)
