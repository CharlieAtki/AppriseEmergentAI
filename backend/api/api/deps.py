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
from core.repositories.task_repository import TaskRepository
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession


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

        ws = await session.get(Workspace, workspace_id)
        if ws is None or ws.organisation_id != org_id:
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
