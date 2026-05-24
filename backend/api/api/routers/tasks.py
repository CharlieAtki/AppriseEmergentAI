from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.eventing.activity.task_logger import TaskActivityLogger
from core.intelligence.call_types import CallType
from core.intelligence.enrichment import enrich_rule_based
from core.intelligence.prompts import enrich as enrich_prompt
from core.models.tasks import Task
from api.deps import get_db, require_workspace
from api.schemas.task import CreateTaskRequest, TaskCreatedResponse, TaskResponse
from api.services.task_service import TaskService

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> TaskService:
    return TaskService(session)


async def enrich_and_release(task_id: uuid.UUID, publish, llm_router) -> None:
    """Background task: hybrid enrichment → 'open' → publish TaskCreatedEvent.

    Rule-based path runs first (confidence threshold 0.85). Below threshold the
    task escalates to a single LLM call (CallType.ENRICH). Either way the task
    transitions from 'enriching' to 'open' and fires task_logger.created(task),
    which triggers TaskCreatedRedisPublisher → XADD stream:task → worker bidding.
    """
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return

        result = enrich_rule_based(task.title, task.description)

        if result.confidence < 0.85:
            try:
                raw = await llm_router.complete(
                    enrich_prompt.build_prompt(task.title, task.description or ""),
                    CallType.ENRICH,
                    json_mode=True,
                )
                parsed = enrich_prompt.parse(raw)
                task.required_skills = parsed.required_skills
                task.difficulty = parsed.difficulty
                task.task_type = parsed.task_type
                task.domain_tags = parsed.domain_tags
            except Exception:
                task.required_skills = result.required_skills
                task.difficulty = result.difficulty
                task.task_type = result.task_type
                task.domain_tags = result.domain_tags
        else:
            task.required_skills = result.required_skills
            task.difficulty = result.difficulty
            task.task_type = result.task_type
            task.domain_tags = result.domain_tags

        task.status = "open"

    task_logger = TaskActivityLogger(publish)
    await task_logger.created(task)


@router.post("", response_model=TaskCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    body: CreateTaskRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    workspace=Depends(require_workspace("write")),
    service: TaskService = Depends(get_service),
) -> TaskCreatedResponse:
    task = await service.create(
        workspace_id=workspace.id,
        organisation_id=workspace.organisation_id,
        body=body,
    )
    await service.commit()
    bus = request.app.state.bus
    background_tasks.add_task(enrich_and_release, task.id, bus.apublish, request.app.state.llm_router)
    return TaskCreatedResponse(task_id=task.id, status=task.status, workspace_id=task.workspace_id)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    workspace=Depends(require_workspace("read")),
    service: TaskService = Depends(get_service),
) -> TaskResponse:
    task = await service.get(workspace.id, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    workspace=Depends(require_workspace("read")),
    service: TaskService = Depends(get_service),
) -> list[TaskResponse]:
    tasks = await service.list(workspace.id)
    return [TaskResponse.model_validate(t) for t in tasks]