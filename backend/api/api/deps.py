from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable

from arq import ArqRedis
from core.database import get_session
from core.eventing.activity.agent_logger import AgentActivityLogger
from core.eventing.activity.base import PublishFn
from core.eventing.activity.task_logger import TaskActivityLogger
from core.eventing.bus.in_process_bus import EventBus
from core.intelligence.llm_router import LLMRouter
from core.models.tenant import Workspace
from core.repositories.agent_repository import AgentRepository
from core.repositories.api_key_repository import ApiKeyRepository
from core.repositories.task_execution_repository import TaskExecutionRepository
from core.repositories.task_repository import TaskRepository
from core.repositories.tool_repository import ToolRepository
from core.repositories.workspace_repository import WorkspaceRepository
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.agent_service import AgentService
from api.services.api_key_service import ApiKeyService
from api.services.task_service import TaskService
from api.services.workspace_service import WorkspaceService
from api.services.workspace_tool_service import WorkspaceToolService


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus  # type: ignore[no-any-return]


def get_event_publisher(bus: EventBus = Depends(get_bus)) -> PublishFn:
    return bus.apublish


def get_task_activity_logger(
    publish: PublishFn = Depends(get_event_publisher),
) -> TaskActivityLogger:
    return TaskActivityLogger(publish)


def get_agent_activity_logger(
    publish: PublishFn = Depends(get_event_publisher),
) -> AgentActivityLogger:
    return AgentActivityLogger(publish)


def get_redis(request: Request) -> Redis:
    return request.app.state.redis  # type: ignore[no-any-return]


def get_llm_router(request: Request) -> LLMRouter:
    return request.app.state.llm_router  # type: ignore[no-any-return]


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with get_session() as session:
        yield session


def get_task_repo(session: AsyncSession = Depends(get_db)) -> TaskRepository:
    return TaskRepository(session)


def get_agent_repo(session: AsyncSession = Depends(get_db)) -> AgentRepository:
    return AgentRepository(session)


def get_workspace_repo(session: AsyncSession = Depends(get_db)) -> WorkspaceRepository:
    return WorkspaceRepository(session)


def get_workspace_service(
    repo: WorkspaceRepository = Depends(get_workspace_repo),
) -> WorkspaceService:
    return WorkspaceService(repo)


def get_task_service(repo: TaskRepository = Depends(get_task_repo)) -> TaskService:
    return TaskService(repo)


def get_task_execution_repo(session: AsyncSession = Depends(get_db)) -> TaskExecutionRepository:
    return TaskExecutionRepository(session)


def get_agent_service(
    repo: AgentRepository = Depends(get_agent_repo),
    exec_repo: TaskExecutionRepository = Depends(get_task_execution_repo),
) -> AgentService:
    return AgentService(repo, exec_repo)


def get_api_key_repo(session: AsyncSession = Depends(get_db)) -> ApiKeyRepository:
    return ApiKeyRepository(session)


def get_api_key_service(repo: ApiKeyRepository = Depends(get_api_key_repo)) -> ApiKeyService:
    return ApiKeyService(repo)


def get_tool_repo(session: AsyncSession = Depends(get_db)) -> ToolRepository:
    return ToolRepository(session)


def get_workspace_tool_service(
    repo: ToolRepository = Depends(get_tool_repo),
) -> WorkspaceToolService:
    return WorkspaceToolService(repo)


def get_arq_queue(request: Request) -> ArqRedis:
    return request.app.state.arq_queue  # type: ignore[no-any-return]


def require_workspace(permission: str = "write") -> Callable[..., Awaitable[Workspace]]:
    """Dep factory: loads Workspace from DB, verifies org ownership and active status.

    Returns the Workspace ORM model. Routes receive it as a typed object and read
    workspace.organisation_id / workspace.id directly — no hardcoded stubs.
    """

    async def dep(
        workspace_id: uuid.UUID,
        request: Request,
        session: AsyncSession = Depends(get_db),
    ) -> Workspace:
        auth = request.state.auth
        org_id = getattr(auth, "org_id", None)
        if org_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorised")

        ws = await WorkspaceRepository(session).get(org_id=org_id, workspace_id=workspace_id)
        if ws is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

        if ws.status != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Workspace is not active"
            )

        if permission == "write":
            scopes = getattr(auth, "scopes", None)
            if scopes is not None and "tasks:write" not in scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission"
                )

        return ws

    return dep
