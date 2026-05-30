from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.eventing.activity.task_logger import TaskActivityLogger
from core.intelligence.enrichment import EnrichmentOverrides, enrich
from core.models.tasks import Task
from api.deps import get_db, require_workspace
from api.schemas.task import CreateTaskRequest, TaskCreatedResponse, TaskOverrides, TaskResponse
from api.services.task_service import TaskService

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> TaskService:
    return TaskService(session)


async def enrich_and_release(
    task_id: uuid.UUID,
    publish,
    llm_router,
    overrides: EnrichmentOverrides | None = None,
) -> None:
    """Background task: enrichment → 'open' → publish TaskCreatedEvent.

    All enrichment logic lives in core.intelligence.enrichment.enrich(). This
    function owns only the ORM write and event publish.
    """
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return

        result = await enrich(task.title, task.description, llm_router, overrides)
        task.required_skills = result.required_skills
        task.difficulty      = result.difficulty
        task.task_type       = result.task_type
        task.domain_tags     = result.domain_tags
        task.status          = "open"

    task_logger = TaskActivityLogger(publish)
    await task_logger.created(task)


@router.post("", response_model=TaskCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    body: CreateTaskRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
    workspace=Depends(require_workspace("write")),
    service: TaskService = Depends(get_service),
) -> TaskCreatedResponse:
    task = await service.create(
        workspace_id=workspace.id,
        organisation_id=workspace.organisation_id,
        body=body,
        idempotency_key=idempotency_key_header,
    )
    await service.commit()
    bus = request.app.state.bus
    ov = (
        EnrichmentOverrides(
            task_type=body.overrides.task_type,
            required_skills=body.overrides.required_skills,
            difficulty=body.overrides.difficulty,
        )
        if body.overrides else None
    )
    background_tasks.add_task(enrich_and_release, task.id, bus.apublish, request.app.state.llm_router, ov)
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