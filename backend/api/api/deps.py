from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable

from arq import ArqRedis
from core.config import settings as core_settings
from core.database import get_session
from core.eventing.activity.base import PublishFn
from core.eventing.bus.in_process_bus import EventBus
from core.intelligence.llm_router import LLMRouter
from core.models.tenant import Organisation, Workspace
from core.repositories.agent_repository import AgentRepository
from core.repositories.api_key_repository import ApiKeyRepository
from core.repositories.org_repository import OrganisationRepository
from core.repositories.task_execution_repository import TaskExecutionRepository
from core.repositories.task_repository import TaskRepository
from core.repositories.tool_repository import ToolRepository
from core.repositories.user_repository import UserRepository
from core.repositories.workspace_metrics_repository import WorkspaceMetricsRepository
from core.repositories.workspace_repository import WorkspaceRepository
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.agent_service import AgentService
from api.services.api_key_service import ApiKeyService
from api.services.centrifugo_proxy_service import CentrifugoProxyService
from api.services.coordination_config_service import CoordinationConfigService
from api.services.task_service import TaskService
from api.services.workspace_observability_service import WorkspaceObservabilityService
from api.services.workspace_service import WorkspaceService
from api.services.workspace_stream_service import WorkspaceStreamService
from api.services.workspace_tool_service import WorkspaceToolService


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus  # type: ignore[no-any-return]


def get_event_publisher(bus: EventBus = Depends(get_bus)) -> PublishFn:
    return bus.apublish


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


def get_workspace_metrics_repo(
    session: AsyncSession = Depends(get_db),
) -> WorkspaceMetricsRepository:
    return WorkspaceMetricsRepository(session)


def get_workspace_observability_service(
    repo: WorkspaceMetricsRepository = Depends(get_workspace_metrics_repo),
) -> WorkspaceObservabilityService:
    return WorkspaceObservabilityService(repo)


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
) -> WorkspaceStreamService:
    return WorkspaceStreamService(agent_service, metrics_repo)


def get_org_repo(session: AsyncSession = Depends(get_db)) -> OrganisationRepository:
    return OrganisationRepository(session)


def get_coordination_config_service(
    org_repo: OrganisationRepository = Depends(get_org_repo),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repo),
) -> CoordinationConfigService:
    return CoordinationConfigService(org_repo, workspace_repo)


def require_organisation(permission: str = "write") -> Callable[..., Awaitable[Organisation]]:
    """Dep factory: loads Organisation from DB, verifies the caller belongs to it.

    Mirrors require_workspace()'s shape exactly so the route signature never has
    to change when real role checks land — only this function's body does.
    """

    async def dep(
        org_id: uuid.UUID,
        request: Request,
        org_repo: OrganisationRepository = Depends(get_org_repo),
    ) -> Organisation:
        auth = request.state.auth
        auth_org_id = getattr(auth, "org_id", None)
        if auth_org_id is None or auth_org_id != org_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorised")

        # ApiKeyPayload carries org_id alongside workspace_id, but API keys are
        # workspace-scoped credentials by design (see ApiKeyService) — a key
        # issued for one workspace must not be able to write org-wide config
        # that silently affects every other workspace in that org. This is a
        # hard boundary, not a roles nuance: block it outright rather than
        # deferring it to the same TODO as member-vs-admin permission checks.
        if getattr(auth, "auth_type", None) == "api_key":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API keys are workspace-scoped; organisation-level configuration requires a user session",
            )

        org = await org_repo.get_by_id(org_id)
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found"
            )

        # TODO(roles): OrganisationMember.role exists on the model but is never
        # read into request.state.auth today. Once role-based permissions land,
        # gate `permission` against the caller's role here. Until then this only
        # checks membership — identical in strength to require_workspace() before
        # workspace roles existed.
        return org

    return dep


def get_user_repo(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)


def get_centrifugo_proxy_service(
    org_repo: OrganisationRepository = Depends(get_org_repo),
    user_repo: UserRepository = Depends(get_user_repo),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    stream_service: WorkspaceStreamService = Depends(get_workspace_stream_service),
) -> CentrifugoProxyService:
    return CentrifugoProxyService(org_repo, user_repo, workspace_service, stream_service)


def require_centrifugo_proxy_secret(request: Request) -> None:
    """Auth guard for Centrifugo's connect/subscribe proxy callbacks — a shared
    secret header, not Clerk/API-key (those routes are exempt from AuthMiddleware;
    see EXEMPT_PREFIXES in api/middleware/auth.py). Centrifugo's proxy calls carry
    this header on every callback per its own proxy configuration."""
    secret = core_settings.centrifugo.proxy_secret.get_secret_value()
    if not secret or request.headers.get("X-Centrifugo-Proxy-Secret") != secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorised")


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


def require_workspace(
    permission: str = "write", *, require_active: bool = True
) -> Callable[..., Awaitable[Workspace]]:
    """Dep factory: loads Workspace from DB, verifies org ownership and (by default) active status.

    Returns the Workspace ORM model. Routes receive it as a typed object and read
    workspace.organisation_id / workspace.id directly — no hardcoded stubs.

    require_active=True is right for routes that operate *inside* an active
    workspace (create task, create agent, etc.) — those must be blocked while
    paused. It's wrong for the workspace's own lifecycle routes (PATCH to
    reactivate a paused workspace, DELETE a paused/archived one) — those need
    ownership+scope checks but must not be gated on the very status they exist
    to change. Pass require_active=False for those.
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

        if require_active and not Workspace.is_active_status(ws.status):
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
