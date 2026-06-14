"""Tests for AgentCreditHandler and compute_delegation_credits.

Credit attribution determines which agents gain influence from a completed task.
Silent errors here cause influence drift — agents that should gain don't, or
gain when they shouldn't. The subtask timing invariant (only credit on last
sibling) is the most likely source of regression.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import settings
from worker.handlers.agent_credit import AgentCreditHandler, compute_delegation_credits

# ── compute_delegation_credits (pure aside from session) ──────────────────────


async def test_delegation_credits_decompose_full_signal():
    """Decompose execution → full quality signal."""
    agent_id = uuid.uuid4()
    quality = 0.8

    result_mock = MagicMock()
    result_mock.all.return_value = [(agent_id, "decompose")]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)

    credits_entries = await compute_delegation_credits(
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        quality=quality,
        session=session,
    )

    assert credits_entries == [(agent_id, quality)]


async def test_delegation_credits_cfp_partial_signal():
    """CFP execution: quality * CFP_COORDINATOR_CREDIT (0.5)."""
    agent_id = uuid.uuid4()
    quality = 1.0

    result_mock = MagicMock()
    result_mock.all.return_value = [(agent_id, "cfp")]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)

    credits = await compute_delegation_credits(
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        quality=quality,
        session=session,
    )

    assert len(credits) == 1
    assert credits[0][0] == agent_id
    assert credits[0][1] == pytest.approx(quality * settings.CFP_COORDINATOR_CREDIT)


async def test_delegation_credits_mixed_chain():
    """Both decompose and CFP in the same chain → two credit entries."""
    decompose_agent = uuid.uuid4()
    cfp_agent = uuid.uuid4()
    quality = 0.6

    result_mock = MagicMock()
    result_mock.all.return_value = [
        (decompose_agent, "decompose"),
        (cfp_agent, "cfp"),
    ]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)

    credits = await compute_delegation_credits(
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        quality=quality,
        session=session,
    )

    assert len(credits) == 2
    decompose_credit = next(c for c in credits if c[0] == decompose_agent)
    cfp_credit = next(c for c in credits if c[0] == cfp_agent)
    assert decompose_credit[1] == pytest.approx(quality)
    assert cfp_credit[1] == pytest.approx(quality * settings.CFP_COORDINATOR_CREDIT)


async def test_delegation_credits_no_rows_returns_empty():
    result_mock = MagicMock()
    result_mock.all.return_value = []

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)

    credits = await compute_delegation_credits(
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        quality=0.5,
        session=session,
    )
    assert credits == []


# ── AgentCreditHandler.handle gate ───────────────────────────────────────────


async def test_non_completed_status_no_db_call(make_updated_event, mocker):
    """Handle() must return immediately when status ≠ 'completed'."""
    mock_gs = mocker.patch("worker.handlers.agent_credit.get_session")
    event = make_updated_event("executing", "failed")

    handler = AgentCreditHandler()
    await handler.handle(event)
    mock_gs.assert_not_called()


async def test_no_status_change_no_db_call(make_updated_event, mocker):
    mock_gs = mocker.patch("worker.handlers.agent_credit.get_session")
    event = make_updated_event("completed", "completed")

    handler = AgentCreditHandler()
    await handler.handle(event)
    mock_gs.assert_not_called()


# ── Executor credit path ──────────────────────────────────────────────────────


async def _run_executor_credit(make_updated_event, mocker, agent_influence=0.0):
    agent_id = uuid.uuid4()
    exec_id = uuid.uuid4()

    agent = MagicMock()
    agent.id = agent_id
    agent.influence = agent_influence
    agent.organisation_id = uuid.uuid4()
    agent.workspace_id = uuid.uuid4()

    session = AsyncMock()
    session.get = AsyncMock(return_value=agent)
    # execute for coordinator query → no rows (root task, no delegation)
    exec_result = MagicMock()
    exec_result.all.return_value = []
    session.execute = AsyncMock(return_value=exec_result)

    @asynccontextmanager
    async def _gs():
        yield session

    mocker.patch("worker.handlers.agent_credit.get_session", _gs)

    event = make_updated_event(
        "executing",
        "completed",
        execution_path="self_execute",
        executing_agent_id=agent_id,
        execution_id=exec_id,
        quality_score=0.8,
        parent_task_id=None,
    )
    handler = AgentCreditHandler()
    await handler.handle(event)
    return agent, session


async def test_executor_credit_updates_influence(make_updated_event, mocker):
    """Self-execute completion → agent.influence is updated via EMA."""
    agent, _ = await _run_executor_credit(make_updated_event, mocker, agent_influence=0.0)
    assert agent.influence == pytest.approx(0.12, abs=1e-6)


async def test_executor_credit_adds_influence_snapshot(make_updated_event, mocker):
    """An InfluenceSnapshot must be session.add()'d for the audit trail."""
    from worker.handlers import agent_credit as agent_credit_module

    _, session = await _run_executor_credit(make_updated_event, mocker)
    added_objects = [call.args[0] for call in session.add.call_args_list]
    assert any(isinstance(obj, agent_credit_module.InfluenceSnapshot) for obj in added_objects)


async def test_non_self_execute_skips_executor_credit(make_updated_event, mocker):
    """Decompose path → no executor credit, even if quality_score is set."""
    agent_id = uuid.uuid4()
    agent = MagicMock()
    agent.id = agent_id
    agent.influence = 0.5

    session = AsyncMock()
    session.get = AsyncMock(return_value=agent)
    exec_result = MagicMock()
    exec_result.all.return_value = []
    session.execute = AsyncMock(return_value=exec_result)

    @asynccontextmanager
    async def _gs():
        yield session

    mocker.patch("worker.handlers.agent_credit.get_session", _gs)

    event = make_updated_event(
        "executing",
        "completed",
        execution_path="decompose",
        executing_agent_id=agent_id,
        quality_score=0.9,
        parent_task_id=None,
    )
    handler = AgentCreditHandler()
    await handler.handle(event)

    # Influence must not change
    assert agent.influence == 0.5


# ── Coordinator credit — subtask timing ──────────────────────────────────────


async def test_subtask_non_last_sibling_no_credit(make_updated_event, mocker):
    """If another sibling is still running, no coordinator credit is issued."""
    parent_id = uuid.uuid4()

    sibling1 = MagicMock()
    sibling1.status = "completed"
    sibling2 = MagicMock()
    sibling2.status = "executing"  # still running

    siblings_result = MagicMock()
    siblings_result.scalars.return_value.all.return_value = [sibling1, sibling2]

    session = AsyncMock()
    session.get = AsyncMock(return_value=None)  # no executor agent (path != self_execute)
    session.execute = AsyncMock(return_value=siblings_result)

    @asynccontextmanager
    async def _gs():
        yield session

    mocker.patch("worker.handlers.agent_credit.get_session", _gs)

    event = make_updated_event(
        "executing",
        "completed",
        execution_path="self_execute",
        executing_agent_id=None,
        quality_score=0.7,
        parent_task_id=parent_id,
    )
    handler = AgentCreditHandler()
    await handler.handle(event)

    # Only the siblings execute query should have run; no delegation query
    assert session.execute.call_count == 1


async def test_subtask_last_sibling_triggers_coordinator_credit(make_updated_event, mocker):
    """When this is the last sibling, coordinator credit flows to parent's chain."""
    parent_id = uuid.uuid4()
    coord_agent_id = uuid.uuid4()
    coord_agent = MagicMock()
    coord_agent.id = coord_agent_id
    coord_agent.influence = 0.0
    coord_agent.organisation_id = uuid.uuid4()
    coord_agent.workspace_id = uuid.uuid4()

    sibling = MagicMock()
    sibling.id = uuid.uuid4()
    sibling.status = "completed"  # only one, already terminal

    avg_quality = 0.7

    siblings_result = MagicMock()
    siblings_result.scalars.return_value.all.return_value = [sibling]

    avg_result = MagicMock()
    avg_result.scalar.return_value = avg_quality

    delegation_result = MagicMock()
    delegation_result.all.return_value = [(coord_agent_id, "decompose")]

    session = AsyncMock()
    # _credit_executor returns immediately when execution_path=None (no session.get call).
    # Only one get call occurs: in _credit_coordinator for the coordinator agent.
    session.get = AsyncMock(return_value=coord_agent)
    session.execute = AsyncMock(side_effect=[siblings_result, avg_result, delegation_result])

    @asynccontextmanager
    async def _gs():
        yield session

    mocker.patch("worker.handlers.agent_credit.get_session", _gs)

    event = make_updated_event(
        "executing",
        "completed",
        execution_path=None,
        executing_agent_id=None,
        quality_score=None,
        parent_task_id=parent_id,
    )
    handler = AgentCreditHandler()
    await handler.handle(event)

    # Coordinator agent's influence should be updated
    expected = 0.0 + settings.INFLUENCE_EMA_ALPHA * (avg_quality - 0.0)
    assert coord_agent.influence == pytest.approx(expected, abs=1e-6)
