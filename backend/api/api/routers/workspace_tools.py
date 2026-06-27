from __future__ import annotations

import uuid

from core.models.tenant import Workspace
from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_workspace_tool_service, require_workspace
from api.schemas.workspace_tool import EnableToolRequest, WorkspaceToolResponse
from api.services.workspace_tool_service import EnableToolCommand, WorkspaceToolService

router = APIRouter()


@router.get("", response_model=list[WorkspaceToolResponse])
async def list_workspace_tools(
    workspace: Workspace = Depends(require_workspace("read")),
    service: WorkspaceToolService = Depends(get_workspace_tool_service),
) -> list[WorkspaceToolResponse]:
    tools = await service.list_tools(workspace_id=workspace.id)
    return [WorkspaceToolResponse.model_validate(t) for t in tools]


@router.put("/{tool_id}", response_model=WorkspaceToolResponse)
async def enable_workspace_tool(
    tool_id: uuid.UUID,
    body: EnableToolRequest,
    workspace: Workspace = Depends(require_workspace("write")),
    service: WorkspaceToolService = Depends(get_workspace_tool_service),
) -> WorkspaceToolResponse:
    cmd = EnableToolCommand(workspace_id=workspace.id, tool_id=tool_id, config=body.config)
    result = await service.enable_tool(cmd)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return WorkspaceToolResponse.model_validate(result)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_workspace_tool(
    tool_id: uuid.UUID,
    workspace: Workspace = Depends(require_workspace("write")),
    service: WorkspaceToolService = Depends(get_workspace_tool_service),
) -> None:
    removed = await service.disable_tool(workspace_id=workspace.id, tool_id=tool_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tool not enabled in this workspace"
        )
