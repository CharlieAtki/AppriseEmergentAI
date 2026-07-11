from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from api.services.workspace_observability_service import WorkspaceObservabilityService


def _make_event(gini: float = 0.5) -> MagicMock:
    event = MagicMock()
    event.id = uuid.uuid4()
    event.event_type = "hub_detected"
    event.gini_coefficient = gini
    event.hub_agent_id = uuid.uuid4()
    event.recorded_at = datetime.now(UTC)
    return event


async def test_get_emergence_events_returns_empty_list_when_none_recorded():
    metrics_repo = AsyncMock()
    emergence_repo = AsyncMock()
    emergence_repo.list_recent.return_value = []
    service = WorkspaceObservabilityService(metrics_repo, emergence_repo)

    result = await service.get_emergence_events(uuid.uuid4())

    assert result == []


async def test_get_emergence_events_maps_domain_to_dto():
    metrics_repo = AsyncMock()
    emergence_repo = AsyncMock()
    event = _make_event(gini=0.72)
    emergence_repo.list_recent.return_value = [event]
    service = WorkspaceObservabilityService(metrics_repo, emergence_repo)

    result = await service.get_emergence_events(uuid.uuid4())

    assert len(result) == 1
    assert result[0].id == event.id
    assert result[0].gini_coefficient == 0.72
    assert result[0].hub_agent_id == event.hub_agent_id


async def test_get_emergence_events_passes_since_until_limit_through():
    metrics_repo = AsyncMock()
    emergence_repo = AsyncMock()
    emergence_repo.list_recent.return_value = []
    service = WorkspaceObservabilityService(metrics_repo, emergence_repo)
    workspace_id = uuid.uuid4()
    since = datetime(2026, 1, 1, tzinfo=UTC)
    until = datetime(2026, 2, 1, tzinfo=UTC)

    await service.get_emergence_events(workspace_id, since=since, until=until, limit=10)

    emergence_repo.list_recent.assert_awaited_once_with(
        workspace_id, since=since, until=until, limit=10
    )
