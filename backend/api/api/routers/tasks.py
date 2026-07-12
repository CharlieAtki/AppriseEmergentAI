from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime

from arq import ArqRedis
from core.intelligence.enrichment import EnrichmentOverrides
from core.models.tenant import Workspace
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_arq_queue, get_db, get_task_service, require_workspace
from api.schemas.task import CreateTaskRequest, TaskCreatedResponse, TaskResponse
from api.services.task_service import CreateTaskCommand, TaskService

router = APIRouter()


@router.post("", response_model=TaskCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    body: CreateTaskRequest,
    idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
    workspace: Workspace = Depends(require_workspace("write")),
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_db),
    arq_queue: ArqRedis = Depends(get_arq_queue),
) -> TaskCreatedResponse:
    """Create a task and enqueue enrichment as a durable ARQ job.

    Commits the task row explicitly before enqueuing enrich_task so the job's
    fresh session is guaranteed to see it. service and session share the same
    AsyncSession instance — FastAPI deduplicates Depends(get_db).
    """
    cmd = CreateTaskCommand(
        workspace_id=workspace.id,
        organisation_id=workspace.organisation_id,
        title=body.title,
        description=body.description,
        task_type=body.task_type,
        priority=body.priority,
        deadline_at=body.deadline_at,
        external_ref=body.external_ref,
        idempotency_key=idempotency_key_header,
        overrides=(
            EnrichmentOverrides(
                task_type=body.overrides.task_type,
                required_skills=body.overrides.required_skills,
                difficulty=body.overrides.difficulty,
            )
            if body.overrides
            else None
        ),
    )
    task = await service.create(cmd)
    await session.commit()

    ov_dict = dataclasses.asdict(cmd.overrides) if cmd.overrides else None
    await arq_queue.enqueue_job(
        "enrich_task",
        task_id=str(task.id),
        workspace_id=str(workspace.id),
        overrides=ov_dict,
    )
    return TaskCreatedResponse(task_id=task.id, status=task.status, workspace_id=task.workspace_id)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    workspace: Workspace = Depends(require_workspace("read")),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """Fetch one task's detail.

    Known gap: agent_id is always null here (unlike list_tasks, this path doesn't
    join the latest TaskExecution) and the response carries no execution/bid
    history, tool trace, or failure reasoning. Extend this endpoint with that once
    a detail view needs to fetch it on demand — the live task feed panel's expand
    interaction is the first caller that will want it.
    """
    task = await service.get(task_id, workspace.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    since: datetime | None = Query(None),
    limit: int | None = Query(None, ge=1, le=500),
    workspace: Workspace = Depends(require_workspace("read")),
    service: TaskService = Depends(get_task_service),
) -> list[TaskResponse]:
    tasks = await service.list(workspace.id, since=since, limit=limit)
    return [TaskResponse.model_validate(t) for t in tasks]
