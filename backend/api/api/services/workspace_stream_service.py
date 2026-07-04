from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass

from core.models.tenant import Workspace
from core.repositories.workspace_metrics_repository import WorkspaceMetricsRepository
from redis.asyncio import Redis

from api.services.agent_service import AgentData, AgentService
from api.services.auth_service import WsTicketPayload, ws_ticket_key
from api.services.workspace_observability_service import WorkspaceMetricsData

WS_TICKET_TTL_SECONDS = 30


@dataclass(frozen=True)
class StreamTicketData:
    """Single-use WebSocket connect ticket — the router serialises this to the client."""

    ticket: str


@dataclass(frozen=True)
class WorkspaceStreamSnapshotData:
    """Initial payload sent on WS connect — the agent pool + latest metrics snapshot."""

    agents: list[AgentData]
    metrics: WorkspaceMetricsData | None


class WorkspaceStreamService:
    """Live-dashboard boundary — ticket minting + initial snapshot; ORM never escapes.

    Kept separate from WorkspaceService (pure CRUD) — matches this codebase's
    one-class-one-job discipline. Composes AgentService (reuses AgentData) rather
    than reaching around it to AgentRepository directly.

    Depends on WorkspaceMetricsRepository directly rather than
    WorkspaceObservabilityService — get_latest_metrics() there has no policy logic
    beyond repo.get_latest() + WorkspaceMetricsData.from_domain(), so the reusable
    unit is the DTO's from_domain() classmethod, not a service instance. Services
    depending on services has no other precedent in this codebase; this keeps the
    dependency graph flat (services → repositories) rather than establishing a new
    pattern for a case with no policy to protect.
    """

    def __init__(
        self,
        agent_service: AgentService,
        metrics_repo: WorkspaceMetricsRepository,
        redis: Redis,
    ) -> None:
        self._agent_service = agent_service
        self._metrics_repo = metrics_repo
        self._redis = redis

    async def mint_stream_ticket(self, workspace: Workspace, org_id: uuid.UUID) -> StreamTicketData:
        token = secrets.token_urlsafe(32)
        payload = WsTicketPayload(org_id=org_id, workspace_id=workspace.id)
        # Key is scoped by workspace_id (ws_ticket_key(), auth_service.py) — a ticket
        # presented against the wrong workspace path can't even be found, so it's
        # never consumed by a mismatched request. Validating workspace_id only
        # after GETDEL would burn a legitimate ticket without granting access.
        await self._redis.setex(
            ws_ticket_key(workspace.id, token), WS_TICKET_TTL_SECONDS, payload.model_dump_json()
        )
        return StreamTicketData(ticket=token)

    async def get_initial_snapshot(self, workspace_id: uuid.UUID) -> WorkspaceStreamSnapshotData:
        agents = await self._agent_service.list_active(workspace_id)
        snapshot = await self._metrics_repo.get_latest(workspace_id)
        metrics = WorkspaceMetricsData.from_domain(snapshot) if snapshot is not None else None
        return WorkspaceStreamSnapshotData(agents=agents, metrics=metrics)
