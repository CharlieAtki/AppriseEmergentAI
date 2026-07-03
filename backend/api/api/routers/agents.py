from __future__ import annotations

import uuid

from core.models.tenant import Workspace
from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_agent_service, require_workspace
from api.schemas.agent import AgentResponse, CreateAgentRequest, UpdateAgentRequest
from api.services.agent_service import AgentService, CreateAgentCommand, UpdateAgentCommand

router = APIRouter()


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentRequest,
    workspace: Workspace = Depends(require_workspace("write")),
    service: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    cmd = CreateAgentCommand(
        workspace_id=workspace.id,
        organisation_id=workspace.organisation_id,
        name=body.name,
        skills=body.skills,
        personality=body.personality,
    )
    agent = await service.create(cmd)
    return AgentResponse.model_validate(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    workspace: Workspace = Depends(require_workspace("read")),
    service: AgentService = Depends(get_agent_service),
) -> list[AgentResponse]:
    agents = await service.list(workspace_id=workspace.id)
    return [AgentResponse.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    workspace: Workspace = Depends(require_workspace("read")),
    service: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    agent = await service.get(agent_id, workspace.id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: uuid.UUID,
    workspace: Workspace = Depends(require_workspace("write")),
    service: AgentService = Depends(get_agent_service),
) -> None:
    deleted = await service.delete(agent_id, workspace.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: UpdateAgentRequest,
    workspace: Workspace = Depends(require_workspace("write")),
    service: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    cmd = UpdateAgentCommand(name=body.name, status=body.status)
    agent = await service.update(agent_id, workspace.id, cmd)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentResponse.model_validate(agent)
