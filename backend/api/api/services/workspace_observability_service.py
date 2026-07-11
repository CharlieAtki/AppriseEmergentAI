from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from core.models.observability import (
    EmergenceEvent,
    WorkspaceMetricsPayload,
    WorkspaceMetricsSnapshot,
)
from core.repositories.emergence_event_repository import EmergenceEventRepository
from core.repositories.workspace_metrics_repository import WorkspaceMetricsRepository


@dataclass(frozen=True)
class WorkspaceMetricsData:
    """ORM boundary DTO for a Workspace Metrics Snapshot — the routine, periodic
    sample (Gini, specialisation index, agent count), distinct from an Emergence
    Event (a discrete "hub agent detected" occurrence). See docs/backend/CONTEXT.md.
    """

    gini: float
    specialisation_index: float
    agent_count: int
    recorded_at: datetime

    @classmethod
    def from_domain(cls, snapshot: WorkspaceMetricsSnapshot) -> WorkspaceMetricsData:
        # WorkspaceMetricsPayload.from_dict() owns the metrics JSONB key names —
        # the same type worker/jobs/sample_metrics.py uses to write them, so the
        # two sides can never silently drift on a rename.
        payload = WorkspaceMetricsPayload.from_dict(snapshot.metrics)
        return cls(
            gini=payload.gini,
            specialisation_index=payload.specialisation_index,
            agent_count=payload.agent_count,
            recorded_at=snapshot.recorded_at,
        )


@dataclass(frozen=True)
class EmergenceEventData:
    """ORM boundary DTO for an Emergence Event — a discrete "hub agent detected"
    occurrence, distinct from the routine WorkspaceMetricsSnapshot sample."""

    id: uuid.UUID
    event_type: str
    gini_coefficient: float | None
    hub_agent_id: uuid.UUID | None
    recorded_at: datetime

    @classmethod
    def from_domain(cls, event: EmergenceEvent) -> EmergenceEventData:
        return cls(
            id=event.id,
            event_type=event.event_type,
            gini_coefficient=event.gini_coefficient,
            hub_agent_id=event.hub_agent_id,
            recorded_at=event.recorded_at,
        )


class WorkspaceObservabilityService:
    """Boundary for the GET /workspaces/{id}/metrics and GET /workspaces/{id}/emergence
    REST reads — see core/models/observability.py.

    Kept separate from WorkspaceService (pure CRUD) and WorkspaceStreamService
    (WS ticket/connect orchestration). WorkspaceStreamService's WS init payload
    reads WorkspaceMetricsRepository directly rather than through this service
    (no service-to-service dependency for a method with no policy logic) — the
    guarantee against the two paths diverging is WorkspaceMetricsData.from_domain(),
    which both this service and WorkspaceStreamService call for shaping.
    """

    def __init__(
        self,
        metrics_repo: WorkspaceMetricsRepository,
        emergence_repo: EmergenceEventRepository,
    ) -> None:
        self._metrics_repo = metrics_repo
        self._emergence_repo = emergence_repo

    async def get_latest_metrics(self, workspace_id: uuid.UUID) -> WorkspaceMetricsData | None:
        snapshot = await self._metrics_repo.get_latest(workspace_id)
        return WorkspaceMetricsData.from_domain(snapshot) if snapshot is not None else None

    async def get_emergence_events(
        self,
        workspace_id: uuid.UUID,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> list[EmergenceEventData]:
        events = await self._emergence_repo.list_recent(
            workspace_id, since=since, until=until, limit=limit
        )
        return [EmergenceEventData.from_domain(e) for e in events]
