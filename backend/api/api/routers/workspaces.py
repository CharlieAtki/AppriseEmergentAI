from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_workspace
from api.schemas.workspace import CreateWorkspaceRequest, UpdateWorkspaceRequest, WorkspaceResponse
from api.services.workspace_service import WorkspaceService

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> WorkspaceService:
    return WorkspaceService(session)


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    request: Request,
    service: WorkspaceService = Depends(get_service),
) -> WorkspaceResponse:
    org_id = request.state.auth.org_id
    ws = await service.create(org_id=org_id, body=body)
    return WorkspaceResponse.model_validate(ws)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    request: Request,
    service: WorkspaceService = Depends(get_service),
) -> list[WorkspaceResponse]:
    org_id = request.state.auth.org_id
    workspaces = await service.list(org_id=org_id)
    return [WorkspaceResponse.model_validate(ws) for ws in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    request: Request,
    service: WorkspaceService = Depends(get_service),
) -> WorkspaceResponse:
    org_id = request.state.auth.org_id
    ws = await service.get(org_id=org_id, workspace_id=workspace_id)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return WorkspaceResponse.model_validate(ws)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    body: UpdateWorkspaceRequest,
    workspace=Depends(require_workspace("write")),
    service: WorkspaceService = Depends(get_service),
) -> WorkspaceResponse:
    ws = await service.update(workspace, body)
    return WorkspaceResponse.model_validate(ws)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace=Depends(require_workspace("write")),
    service: WorkspaceService = Depends(get_service),
) -> None:
    await service.delete(workspace)
