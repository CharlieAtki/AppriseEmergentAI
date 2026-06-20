from __future__ import annotations

import uuid

from core.models.tenant import Workspace
from core.repositories.agent_repository import AgentRepository
from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_agent_repo, require_workspace
from api.schemas.agent import AgentResponse, CreateAgentRequest, UpdateAgentRequest

router = APIRouter()


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentRequest,
    workspace: Workspace = Depends(require_workspace("write")),
    repo: AgentRepository = Depends(get_agent_repo),
) -> AgentResponse:
    agent = await repo.create(
        workspace_id=workspace.id,
        organisation_id=workspace.organisation_id,
        name=body.name,
        skills=body.skills,
        personality=body.personality,
    )
    return AgentResponse.model_validate(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    workspace: Workspace = Depends(require_workspace("read")),
    repo: AgentRepository = Depends(get_agent_repo),
) -> list[AgentResponse]:
    agents = await repo.list(workspace_id=workspace.id)
    return [AgentResponse.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    workspace: Workspace = Depends(require_workspace("read")),
    repo: AgentRepository = Depends(get_agent_repo),
) -> AgentResponse:
    agent = await repo.get(agent_id, workspace.id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: UpdateAgentRequest,
    workspace: Workspace = Depends(require_workspace("write")),
    repo: AgentRepository = Depends(get_agent_repo),
) -> AgentResponse:
    agent = await repo.get(agent_id, workspace.id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    agent = await repo.update_fields(agent, name=body.name, status=body.status)
    return AgentResponse.model_validate(agent)
