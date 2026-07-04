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
from core.repositories.workspace_metrics_repository import WorkspaceMetricsRepository
from core.repositories.workspace_repository import WorkspaceRepository
from fastapi import Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from api.services.agent_service import AgentService
from api.services.api_key_service import ApiKeyService
from api.services.auth_service import WsTicketPayload, ws_ticket_key
from api.services.task_service import TaskService
from api.services.workspace_observability_service import WorkspaceObservabilityService
from api.services.workspace_service import WorkspaceService
from api.services.workspace_stream_service import WorkspaceStreamService
from api.services.workspace_tool_service import WorkspaceToolService
from api.ws.registry import WorkspaceConnectionRegistry


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


def get_redis(conn: HTTPConnection) -> Redis:
    """HTTPConnection (not Request) — this dependency is reachable from both HTTP
    routes and the WS route (via require_stream_ticket / get_workspace_stream_service).
    Request can't be injected in a websocket scope; HTTPConnection is the common
    base FastAPI resolves for both. See get_workspace_connections() below — same fix."""
    return conn.app.state.redis  # type: ignore[no-any-return]


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


def get_workspace_metrics_repo(
    session: AsyncSession = Depends(get_db),
) -> WorkspaceMetricsRepository:
    return WorkspaceMetricsRepository(session)


def get_workspace_observability_service(
    repo: WorkspaceMetricsRepository = Depends(get_workspace_metrics_repo),
) -> WorkspaceObservabilityService:
    return WorkspaceObservabilityService(repo)


def get_workspace_connections(conn: HTTPConnection) -> WorkspaceConnectionRegistry:
    """HTTPConnection — only ever reached from the WS route, but typed the same way
    as get_redis() for consistency (a plain WebSocket param would also work here)."""
    return conn.app.state.workspace_connections  # type: ignore[no-any-return]


async def require_stream_ticket(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    redis: Redis = Depends(get_redis),
) -> WsTicketPayload:
    """WS-route auth dependency, mirrors require_workspace().

    AuthMiddleware (BaseHTTPMiddleware) never runs for scope["type"] == "websocket",
    so this is the only auth check for GET /workspaces/{id}/stream. Ticket is
    single-use (GETDEL) and 30s-TTL, minted via POST /workspaces/{id}/stream-ticket
    (an ordinary authenticated HTTP route covered by AuthMiddleware as normal).

    The Redis key is scoped by workspace_id (ws_ticket_key()) using the path's
    workspace_id — not the ticket payload's — so a ticket presented against the
    wrong workspace can't even be found, let alone consumed. The payload check
    below is defense-in-depth, not the primary guard: the key scoping is.
    """
    ticket = websocket.query_params.get("ticket")
    raw = await redis.getdel(ws_ticket_key(workspace_id, ticket)) if ticket else None
    if not raw:
        await websocket.close(code=4401)
        raise WebSocketDisconnect

    payload = WsTicketPayload.model_validate_json(raw)
    if payload.workspace_id != workspace_id:
        await websocket.close(code=4401)
        raise WebSocketDisconnect

    return payload


def get_task_service(repo: TaskRepository = Depends(get_task_repo)) -> TaskService:
    return TaskService(repo)


def get_task_execution_repo(session: AsyncSession = Depends(get_db)) -> TaskExecutionRepository:
    return TaskExecutionRepository(session)


def get_agent_service(
    repo: AgentRepository = Depends(get_agent_repo),
    exec_repo: TaskExecutionRepository = Depends(get_task_execution_repo),
) -> AgentService:
    return AgentService(repo, exec_repo)


def get_workspace_stream_service(
    agent_service: AgentService = Depends(get_agent_service),
    metrics_repo: WorkspaceMetricsRepository = Depends(get_workspace_metrics_repo),
    redis: Redis = Depends(get_redis),
) -> WorkspaceStreamService:
    return WorkspaceStreamService(agent_service, metrics_repo, redis)


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
