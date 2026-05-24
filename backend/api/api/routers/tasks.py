from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.eventing.activity.task_logger import TaskActivityLogger
from core.eventing.bus.in_process_bus import EventBus
from api.deps import get_db
from api.schemas.task import CreateTaskRequest, TaskCreatedResponse, TaskResponse
from api.services.task_service import TaskService

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> TaskService:
    return TaskService(session)


def require_workspace(permission: str = "write"):
    """Dep factory: resolves workspace_id + org_id from path param and request.state.

    Stub — real implementation loads the Workspace row from DB, validates the
    caller has at least ``permission`` access, and returns the model. This shape
    is intentional so auth middleware + DB lookup slots in without changing routes.
    """
    def dep(workspace_id: uuid.UUID, request: Request) -> dict:
        auth = getattr(request.state, "auth", {})
        org_id = auth.get("org_id")
        if not org_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorised")
        return {"workspace_id": workspace_id, "organisation_id": org_id}
    return dep


async def enrich_and_release(task_id: uuid.UUID, publish) -> None:
    """Background task: stub enrichment → 'open' → publish TaskCreatedEvent.

    Called immediately after the task row is committed. Transitions the task
    from 'enriching' to 'open' and fires task_logger.created(), which triggers
    TaskCreatedRedisPublisher → XADD stream:task → worker bidding.

    Commit-then-publish ordering is intentional: apublish schedules the
    handler fire-and-forget via ensure_future, so it could otherwise run
    during session.commit() before the write is durable.

    Real enrichment (rule-based fast path + LLM escalation) replaces the
    status assignment below when implemented.
    """
    from core.database import SessionLocal
    from core.models.tasks import Task

    session = SessionLocal()
    try:
        task = await session.get(Task, task_id)
        if task is None:
            return
        task.status = "open"
        await session.commit()  # commit before publishing — expire_on_commit=False keeps attrs cached
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

    task_logger = TaskActivityLogger(publish)
    await task_logger.created(task)


@router.post("", response_model=TaskCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    body: CreateTaskRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    workspace: dict = Depends(require_workspace("write")),
    service: TaskService = Depends(get_service),
    session: AsyncSession = Depends(get_db),
) -> TaskCreatedResponse:
    task = await service.create(
        workspace_id=workspace["workspace_id"],
        organisation_id=workspace["organisation_id"],
        body=body,
    )
    await session.commit()
    bus: EventBus = request.app.state.bus
    background_tasks.add_task(enrich_and_release, task.id, bus.apublish)
    return TaskCreatedResponse(task_id=task.id)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    workspace: dict = Depends(require_workspace("read")),
    service: TaskService = Depends(get_service),
) -> TaskResponse:
    task = await service.get(workspace["workspace_id"], task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    workspace: dict = Depends(require_workspace("read")),
    service: TaskService = Depends(get_service),
) -> list[TaskResponse]:
    tasks = await service.list(workspace["workspace_id"])
    return [TaskResponse.model_validate(t) for t in tasks]
