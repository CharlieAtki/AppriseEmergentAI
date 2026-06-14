"""Tests for ReflectJobHandler gate logic.

The handler must enqueue a reflect job exactly when:
  - status changed to "completed" or "failed"
  - execution_path == "self_execute"
  - executing_agent_id and execution_id are both present

Any other combination is a no-op. Wrong gates would either trigger reflection
on coordinator tasks (wasting LLM calls) or miss it on self-execute tasks
(silently preventing learning).
"""
from __future__ import annotations

import uuid

import pytest

from worker.handlers.reflect_job import ReflectJobHandler


def _handler(arq_mock) -> ReflectJobHandler:
    return ReflectJobHandler(arq_queue=arq_mock)


# ── No-op cases ───────────────────────────────────────────────────────────────

async def test_no_status_change_skips(make_updated_event, arq_mock):
    event = make_updated_event(
        "completed", "completed",  # same → changed("status") = False
        execution_path="self_execute",
        executing_agent_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
    )
    await _handler(arq_mock).handle(event)
    arq_mock.enqueue_job.assert_not_called()


@pytest.mark.parametrize("status", ["open", "reserved", "executing", "expired"])
async def test_non_learning_status_skips(make_updated_event, arq_mock, status):
    event = make_updated_event(
        "open", status,
        execution_path="self_execute",
        executing_agent_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
    )
    await _handler(arq_mock).handle(event)
    arq_mock.enqueue_job.assert_not_called()


@pytest.mark.parametrize("path", ["decompose", "cfp"])
async def test_non_self_execute_path_skips(make_updated_event, arq_mock, path):
    """Decompose and CFP tasks don't self-execute — no reflect needed."""
    event = make_updated_event(
        "executing", "completed",
        execution_path=path,
        executing_agent_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
    )
    await _handler(arq_mock).handle(event)
    arq_mock.enqueue_job.assert_not_called()


async def test_missing_executing_agent_id_skips(make_updated_event, arq_mock):
    event = make_updated_event(
        "executing", "completed",
        execution_path="self_execute",
        executing_agent_id=None,
        execution_id=uuid.uuid4(),
    )
    await _handler(arq_mock).handle(event)
    arq_mock.enqueue_job.assert_not_called()


async def test_missing_execution_id_skips(make_updated_event, arq_mock):
    event = make_updated_event(
        "executing", "completed",
        execution_path="self_execute",
        executing_agent_id=uuid.uuid4(),
        execution_id=None,
    )
    await _handler(arq_mock).handle(event)
    arq_mock.enqueue_job.assert_not_called()


# ── Enqueue cases ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_self_execute_terminal_enqueues_reflect(make_updated_event, arq_mock, status):
    """Both 'completed' and 'failed' self-execute tasks must trigger reflection."""
    agent_id = uuid.uuid4()
    exec_id = uuid.uuid4()

    event = make_updated_event(
        "executing", status,
        execution_path="self_execute",
        executing_agent_id=agent_id,
        execution_id=exec_id,
    )
    await _handler(arq_mock).handle(event)
    arq_mock.enqueue_job.assert_called_once()


async def test_enqueue_args_are_correct(make_updated_event, arq_mock):
    """reflect job must receive IDs as strings and correct status."""
    agent_id = uuid.uuid4()
    exec_id = uuid.uuid4()

    event = make_updated_event(
        "executing", "completed",
        execution_path="self_execute",
        executing_agent_id=agent_id,
        execution_id=exec_id,
    )
    task_id = event.state.id
    ws_id = event.state.workspace_id

    await _handler(arq_mock).handle(event)

    args, kwargs = arq_mock.enqueue_job.call_args
    assert args[0] == "reflect"
    assert kwargs["agent_id"] == str(agent_id)
    assert kwargs["task_id"] == str(task_id)
    assert kwargs["workspace_id"] == str(ws_id)
    assert kwargs["execution_id"] == str(exec_id)
    assert kwargs["status"] == "completed"
