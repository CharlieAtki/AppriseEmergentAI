from __future__ import annotations

import uuid

from core.models.tenant import Workspace
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_workspace
from api.schemas.agent import AgentResponse, CreateAgentRequest, UpdateAgentRequest
from api.services.agent_service import AgentService

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> AgentService:
    return AgentService(session)


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentRequest,
    workspace: Workspace = Depends(require_workspace("write")),
    service: AgentService = Depends(get_service),
) -> AgentResponse:
    agent = await service.create(workspace=workspace, body=body)
    return AgentResponse.model_validate(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    workspace: Workspace = Depends(require_workspace("read")),
    service: AgentService = Depends(get_service),
) -> list[AgentResponse]:
    agents = await service.list(workspace_id=workspace.id)
    return [AgentResponse.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    workspace: Workspace = Depends(require_workspace("read")),
    service: AgentService = Depends(get_service),
) -> AgentResponse:
    agent = await service.get(workspace_id=workspace.id, agent_id=agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: UpdateAgentRequest,
    workspace: Workspace = Depends(require_workspace("write")),
    service: AgentService = Depends(get_service),
) -> AgentResponse:
    agent = await service.get(workspace_id=workspace.id, agent_id=agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    agent = await service.update(agent=agent, body=body)
    return AgentResponse.model_validate(agent)
