"""Tests for RollupSubtaskHandler.

The rollup handler promotes a parent task when all its subtasks reach terminal
status. Bugs here either block parent completion forever or promote prematurely.
The concurrent guard and failed-wins logic are especially regression-sensitive.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.eventing.events.task_events import TaskSnapshot, TaskUpdatedEvent
from worker.handlers.rollup import RollupSubtaskHandler


def _sibling(status: str) -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.status = status
    return s


def _make_handler(arq_mock) -> tuple[RollupSubtaskHandler, AsyncMock]:
    publish = AsyncMock()
    return RollupSubtaskHandler(arq_queue=arq_mock, publish=publish), publish


# ── Early gates (no DB call needed) ──────────────────────────────────────────

async def test_no_status_change_returns_early(make_updated_event, arq_mock, mocker):
    """If status did not change, handle() must return before touching the DB."""
    mock_gs = mocker.patch("worker.handlers.rollup.get_session")
    # Same before/after status → changed("status") is False
    event = make_updated_event("completed", "completed", parent_task_id=uuid.uuid4())
    handler, _ = _make_handler(arq_mock)
    await handler.handle(event)
    mock_gs.assert_not_called()


async def test_non_terminal_status_returns_early(make_updated_event, arq_mock, mocker):
    """Non-terminal status (executing) → return before DB call."""
    mock_gs = mocker.patch("worker.handlers.rollup.get_session")
    event = make_updated_event("open", "executing", parent_task_id=uuid.uuid4())
    handler, _ = _make_handler(arq_mock)
    await handler.handle(event)
    mock_gs.assert_not_called()


async def test_no_parent_task_id_returns_early(make_updated_event, arq_mock, mocker):
    """Root task (parent_task_id=None) → not a subtask, skip."""
    mock_gs = mocker.patch("worker.handlers.rollup.get_session")
    event = make_updated_event("executing", "completed", parent_task_id=None)
    handler, _ = _make_handler(arq_mock)
    await handler.handle(event)
    mock_gs.assert_not_called()


# ── DB path: siblings not all terminal ───────────────────────────────────────

async def test_sibling_still_running_no_enqueue(make_updated_event, arq_mock, mocker):
    """If any sibling is still executing, do not promote parent."""
    parent_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    siblings = [_sibling("completed"), _sibling("executing")]

    session = AsyncMock()
    siblings_result = MagicMock()
    siblings_result.scalars.return_value.all.return_value = siblings
    session.execute = AsyncMock(return_value=siblings_result)

    @asynccontextmanager
    async def _gs():
        yield session

    mocker.patch("worker.handlers.rollup.get_session", _gs)

    event = make_updated_event(
        "executing", "completed",
        parent_task_id=parent_id, workspace_id=ws_id,
    )
    handler, publish = _make_handler(arq_mock)
    await handler.handle(event)

    arq_mock.enqueue_job.assert_not_called()
    publish.assert_not_called()


# ── DB path: parent already terminal (concurrent guard) ───────────────────────

async def test_parent_already_terminal_no_double_rollup(make_updated_event, arq_mock, mocker):
    """If the parent is already completed, skip — another worker already rolled up."""
    parent_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    siblings = [_sibling("completed"), _sibling("failed")]
    parent = MagicMock()
    parent.id = parent_id
    parent.status = "completed"  # already terminal

    session = AsyncMock()
    siblings_result = MagicMock()
    siblings_result.scalars.return_value.all.return_value = siblings
    session.execute = AsyncMock(return_value=siblings_result)
    session.get = AsyncMock(return_value=parent)

    @asynccontextmanager
    async def _gs():
        yield session

    mocker.patch("worker.handlers.rollup.get_session", _gs)

    event = make_updated_event(
        "executing", "completed",
        parent_task_id=parent_id, workspace_id=ws_id,
    )
    handler, publish = _make_handler(arq_mock)
    await handler.handle(event)

    arq_mock.enqueue_job.assert_not_called()
    publish.assert_not_called()


# ── DB path: all siblings terminal — happy paths ──────────────────────────────

async def _run_all_siblings_terminal(
    make_updated_event, arq_mock, mocker,
    sibling_statuses: list[str],
    expected_parent_status: str,
):
    parent_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    exec_id = uuid.uuid4()
    coordinator_id = uuid.uuid4()

    siblings = [_sibling(s) for s in sibling_statuses]
    parent = MagicMock()
    parent.id = parent_id
    parent.status = "executing"  # parent waits in executing while subtasks run
    parent.coordinator_agent_id = coordinator_id
    parent.created_by_agent_id = None

    siblings_result = MagicMock()
    siblings_result.scalars.return_value.all.return_value = siblings

    exec_result = MagicMock()
    exec_result.scalar.return_value = exec_id

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[siblings_result, exec_result])
    session.get = AsyncMock(return_value=parent)

    @asynccontextmanager
    async def _gs():
        yield session

    mocker.patch("worker.handlers.rollup.get_session", _gs)

    event = make_updated_event(
        "executing", sibling_statuses[-1],
        parent_task_id=parent_id, workspace_id=ws_id,
    )
    handler, publish = _make_handler(arq_mock)
    await handler.handle(event)
    return parent, publish


async def test_all_siblings_completed_promotes_parent_completed(
    make_updated_event, arq_mock, mocker,
):
    parent, publish = await _run_all_siblings_terminal(
        make_updated_event, arq_mock, mocker,
        sibling_statuses=["completed", "completed"],
        expected_parent_status="completed",
    )
    assert parent.status == "completed"
    arq_mock.enqueue_job.assert_called_once()
    publish.assert_called_once()


async def test_any_sibling_failed_promotes_parent_failed(
    make_updated_event, arq_mock, mocker,
):
    """failed wins — even one failed sibling makes the parent failed."""
    parent, publish = await _run_all_siblings_terminal(
        make_updated_event, arq_mock, mocker,
        sibling_statuses=["completed", "failed"],
        expected_parent_status="failed",
    )
    assert parent.status == "failed"
    arq_mock.enqueue_job.assert_called_once()


async def test_reflect_job_enqueued_with_correct_args(
    make_updated_event, arq_mock, mocker,
):
    """reflect job must carry agent_id, task_id, workspace_id, execution_id, status."""
    parent_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    exec_id = uuid.uuid4()
    coordinator_id = uuid.uuid4()

    siblings = [_sibling("completed")]
    parent = MagicMock()
    parent.id = parent_id
    parent.status = "executing"  # parent waits in executing while subtasks run
    parent.coordinator_agent_id = coordinator_id
    parent.created_by_agent_id = None

    siblings_result = MagicMock()
    siblings_result.scalars.return_value.all.return_value = siblings
    exec_result = MagicMock()
    exec_result.scalar.return_value = exec_id

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[siblings_result, exec_result])
    session.get = AsyncMock(return_value=parent)

    @asynccontextmanager
    async def _gs():
        yield session

    mocker.patch("worker.handlers.rollup.get_session", _gs)

    event = make_updated_event(
        "executing", "completed",
        parent_task_id=parent_id, workspace_id=ws_id,
    )
    handler, _ = _make_handler(arq_mock)
    await handler.handle(event)

    call_kwargs = arq_mock.enqueue_job.call_args.kwargs
    assert arq_mock.enqueue_job.call_args.args[0] == "reflect"
    assert call_kwargs["agent_id"] == str(coordinator_id)
    assert call_kwargs["task_id"] == str(parent_id)
    assert call_kwargs["workspace_id"] == str(ws_id)
    assert call_kwargs["execution_id"] == str(exec_id)
