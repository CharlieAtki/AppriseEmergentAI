from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from api.services.agent_service import AgentService


def _make_snapshot(agent_id: uuid.UUID, influence: float = 0.4) -> MagicMock:
    snap = MagicMock()
    snap.agent_id = agent_id
    snap.influence = influence
    snap.recorded_at = datetime.now(UTC)
    return snap


def _make_execution(agent_id: uuid.UUID) -> MagicMock:
    execution = MagicMock()
    execution.id = uuid.uuid4()
    execution.agent_id = agent_id
    execution.task_id = uuid.uuid4()
    execution.status = "completed"
    execution.started_at = datetime.now(UTC)
    execution.completed_at = datetime.now(UTC)
    execution.tool_trace = [{"secret": "should-not-leak"}]
    execution.error = None
    return execution


def _make_service() -> tuple[AgentService, AsyncMock, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    exec_repo = AsyncMock()
    influence_repo = AsyncMock()
    service = AgentService(repo, exec_repo, influence_repo)
    return service, repo, exec_repo, influence_repo


async def test_get_influence_history_maps_domain_to_dto():
    service, _repo, _exec_repo, influence_repo = _make_service()
    agent_id = uuid.uuid4()
    influence_repo.list_for_agents.return_value = [_make_snapshot(agent_id, influence=0.9)]

    result = await service.get_influence_history(uuid.uuid4(), [agent_id])

    assert len(result) == 1
    assert result[0].agent_id == agent_id
    assert result[0].influence == 0.9


async def test_get_influence_history_passes_limit_per_agent_mode_through():
    service, _repo, _exec_repo, influence_repo = _make_service()
    influence_repo.list_for_agents.return_value = []
    workspace_id = uuid.uuid4()
    agent_ids = [uuid.uuid4(), uuid.uuid4()]

    await service.get_influence_history(workspace_id, agent_ids, limit_per_agent=5)

    influence_repo.list_for_agents.assert_awaited_once_with(
        workspace_id, agent_ids, since=None, until=None, limit_per_agent=5
    )


async def test_get_task_timeline_excludes_tool_trace_and_error_from_dto():
    service, _repo, exec_repo, _influence_repo = _make_service()
    agent_id = uuid.uuid4()
    execution = _make_execution(agent_id)
    exec_repo.list_for_agents.return_value = [execution]

    result = await service.get_task_timeline(uuid.uuid4(), [agent_id])

    assert len(result) == 1
    entry = result[0]
    assert entry.agent_id == agent_id
    assert entry.status == "completed"
    assert not hasattr(entry, "tool_trace")
    assert not hasattr(entry, "error")


async def test_get_task_timeline_passes_since_until_through():
    service, _repo, exec_repo, _influence_repo = _make_service()
    exec_repo.list_for_agents.return_value = []
    workspace_id = uuid.uuid4()
    agent_ids = [uuid.uuid4()]
    since = datetime(2026, 1, 1, tzinfo=UTC)
    until = datetime(2026, 2, 1, tzinfo=UTC)

    await service.get_task_timeline(workspace_id, agent_ids, since=since, until=until)

    exec_repo.list_for_agents.assert_awaited_once_with(
        workspace_id, agent_ids, since=since, until=until
    )
