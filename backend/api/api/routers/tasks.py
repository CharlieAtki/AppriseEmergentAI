from __future__ import annotations

import dataclasses
import uuid

from arq import ArqRedis
from core.intelligence.enrichment import EnrichmentOverrides
from core.models.tenant import Workspace
from core.repositories.task_repository import TaskRepository
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_arq_queue, get_db, get_task_repo, require_workspace
from api.schemas.task import CreateTaskRequest, TaskCreatedResponse, TaskResponse

router = APIRouter()


@router.post("", response_model=TaskCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    body: CreateTaskRequest,
    idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
    workspace: Workspace = Depends(require_workspace("write")),
    repo: TaskRepository = Depends(get_task_repo),
    session: AsyncSession = Depends(get_db),
    arq_queue: ArqRedis = Depends(get_arq_queue),
) -> TaskCreatedResponse:
    """Create a task and enqueue enrichment as a durable ARQ job.

    Commits the task row explicitly before enqueuing enrich_task so the job's
    fresh session is guaranteed to see it. repo and session share the same
    AsyncSession instance — FastAPI deduplicates Depends(get_db).
    """
    task = await repo.create(
        workspace_id=workspace.id,
        organisation_id=workspace.organisation_id,
        title=body.title,
        description=body.description,
        status="enriching",
        task_type=body.task_type,
        priority=body.priority,
        deadline_at=body.deadline_at,
        external_ref=body.external_ref,
        idempotency_key=idempotency_key_header,
    )
    await session.commit()

    ov_dict = (
        dataclasses.asdict(
            EnrichmentOverrides(
                task_type=body.overrides.task_type,
                required_skills=body.overrides.required_skills,
                difficulty=body.overrides.difficulty,
            )
        )
        if body.overrides
        else None
    )
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
    repo: TaskRepository = Depends(get_task_repo),
) -> TaskResponse:
    task = await repo.get(task_id, workspace.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    workspace: Workspace = Depends(require_workspace("read")),
    repo: TaskRepository = Depends(get_task_repo),
) -> list[TaskResponse]:
    tasks = await repo.list(workspace.id)
    return [TaskResponse.model_validate(t) for t in tasks]
