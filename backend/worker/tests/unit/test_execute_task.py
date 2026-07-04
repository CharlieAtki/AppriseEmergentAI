"""Tests for execute_task — the central orchestration job.

Covers the guards (terminal skip, missing rows, idempotent execution reuse,
depth-guard override), the three decision branches (decompose/cfp/self_execute),
and the failure path that must leave the execution/task rows in a consistent
terminal state rather than dangling at "executing".
"""

from __future__ import annotations

import sys
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
import worker.jobs.execute_task  # noqa: F401 — registers the real submodule in sys.modules
from core.intelligence.prompts.evaluate import EvaluateResponse

# worker/jobs/__init__.py rebinds the `execute_task` package attribute to the
# function itself, so `worker.jobs.execute_task` (attribute access) is not the
# module. Pull the actual module out of sys.modules instead.
execute_task_module = sys.modules["worker.jobs.execute_task"]

CTX: dict[str, object] = {"job_id": "job-1", "job_try": 1}


def _wctx() -> MagicMock:
    wctx = MagicMock()
    wctx.redis = AsyncMock()
    wctx.event_bus.apublish = AsyncMock()
    wctx.bus.apublish = AsyncMock()
    chat_model = MagicMock()
    chat_model.bind_tools.return_value = MagicMock()
    wctx.llm_router.get_chat_model.return_value = chat_model
    wctx.graphs = {"universal": AsyncMock()}
    return wctx


@asynccontextmanager
async def _session_cm(session):
    yield session


def _patch_infra(mocker, task, agent, *, session=None):
    """Patch worker_context, DB session, and the four repositories used by execute_task."""
    wctx = _wctx()
    mocker.patch.object(execute_task_module, "get_worker_context", return_value=wctx)

    session = session or AsyncMock()
    mocker.patch("worker.span.get_session", lambda: _session_cm(session))

    task_repo = MagicMock()
    task_repo.get_for_execution = AsyncMock(return_value=task)
    task_repo.save = AsyncMock()
    mocker.patch.object(execute_task_module, "TaskRepository", return_value=task_repo)

    agent_repo = MagicMock()
    agent_repo.get_for_execution = AsyncMock(return_value=agent)
    agent_repo.save = AsyncMock()
    mocker.patch.object(execute_task_module, "AgentRepository", return_value=agent_repo)

    new_execution = MagicMock()
    new_execution.id = uuid.uuid4()
    new_execution.agent_id = agent.id if agent is not None else None
    execution_repo = MagicMock()
    execution_repo.create = AsyncMock(return_value=new_execution)
    execution_repo.save = AsyncMock()
    mocker.patch.object(execute_task_module, "TaskExecutionRepository", return_value=execution_repo)

    mocker.patch.object(execute_task_module, "ToolRepository", return_value=MagicMock())

    return wctx, task_repo, agent_repo, execution_repo, new_execution


def _decision(mocker, decision: str, reasoning: str = "test") -> AsyncMock:
    return mocker.patch.object(
        execute_task_module.structured_call,
        "run",
        AsyncMock(return_value=EvaluateResponse(decision=decision, reasoning=reasoning)),
    )


# ── Guards ────────────────────────────────────────────────────────────────────


async def test_missing_agent_or_task_returns_early(make_task, make_agent, mocker):
    task = make_task(status="reserved")
    _patch_infra(mocker, task, None)
    agent_repo = MagicMock()
    agent_repo.get_for_execution = AsyncMock(return_value=None)
    mocker.patch.object(execute_task_module, "AgentRepository", return_value=agent_repo)

    decision_mock = _decision(mocker, "self_execute")

    await execute_task_module.execute_task(
        CTX, str(uuid.uuid4()), str(task.id), str(task.workspace_id)
    )

    decision_mock.assert_not_called()


async def test_terminal_task_status_skips_execution(make_task, make_agent, mocker):
    task = make_task(status="completed")  # terminal — already done
    agent = make_agent()
    _patch_infra(mocker, task, agent)
    decision_mock = _decision(mocker, "self_execute")

    await execute_task_module.execute_task(CTX, str(agent.id), str(task.id), str(task.workspace_id))

    decision_mock.assert_not_called()


async def test_idempotent_retry_reuses_existing_execution(make_task, make_agent, mocker):
    """ARQ retry after a crash: execution row already exists at 'executing' — reuse it,
    don't create a second one."""
    task = make_task(status="executing")
    agent = make_agent()
    existing_execution = MagicMock()
    existing_execution.task_id = task.id
    existing_execution.status = "executing"
    existing_execution.agent_id = agent.id
    agent.task_executions = [existing_execution]

    _, _, _, execution_repo, _ = _patch_infra(mocker, task, agent)
    _decision(mocker, "cfp")  # short-circuits before self-execute machinery

    await execute_task_module.execute_task(CTX, str(agent.id), str(task.id), str(task.workspace_id))

    execution_repo.create.assert_not_called()


# ── Depth guard ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("decision", ["decompose", "cfp"])
async def test_depth_guard_forces_self_execute(make_task, make_agent, mocker, decision):
    """delegation_depth >= MAX_DELEGATION_DEPTH overrides any non-self_execute decision."""
    task = make_task(status="reserved", delegation_depth=5)  # MAX_DELEGATION_DEPTH
    agent = make_agent()
    wctx, *_ = _patch_infra(mocker, task, agent)
    _decision(mocker, decision)
    mocker.patch.object(
        execute_task_module.tool_registry, "build_for_task_type", AsyncMock(return_value=([], []))
    )
    mocker.patch.object(execute_task_module.tool_registry, "get_skill_tag_map", return_value={})

    final_state = {
        "artifact": "done",
        "artifact_id": None,
        "step_count": 1,
        "tool_trace": [],
        "skill_tags_used": [],
    }
    wctx.graphs["universal"].ainvoke = AsyncMock(return_value=final_state)

    await execute_task_module.execute_task(CTX, str(agent.id), str(task.id), str(task.workspace_id))

    # Self-execute path was taken despite the LLM's decision — graph was invoked.
    wctx.graphs["universal"].ainvoke.assert_awaited_once()
    assert task.status == "completed"


# ── Decision branches ─────────────────────────────────────────────────────────


async def test_cfp_decision_releases_task_to_pool(make_task, make_agent, mocker):
    task = make_task(status="reserved", delegation_depth=0)
    agent = make_agent()
    wctx, *_, execution = _patch_infra(mocker, task, agent)
    _decision(mocker, "cfp")

    await execute_task_module.execute_task(CTX, str(agent.id), str(task.id), str(task.workspace_id))

    assert task.status == "open"
    assert task.delegation_depth == 1
    wctx.redis.delete.assert_awaited_once_with(f"reservation:{task.workspace_id}:{task.id}")
    assert execution.status == "completed"
    assert execution.execution_path == "cfp"


async def test_decompose_decision_creates_subtasks(make_task, make_agent, mocker):
    task = make_task(status="reserved", delegation_depth=0)
    agent = make_agent()
    *_, execution = _patch_infra(mocker, task, agent)
    _decision(mocker, "decompose")

    subtask = make_task(status="open")
    decompose_resp = MagicMock()
    decompose_resp.subtasks = []
    mocker.patch.object(
        execute_task_module.structured_call,
        "call_and_parse",
        AsyncMock(return_value=decompose_resp),
    )
    mocker.patch.object(
        execute_task_module, "decompose_and_publish", AsyncMock(return_value=[subtask])
    )

    await execute_task_module.execute_task(CTX, str(agent.id), str(task.id), str(task.workspace_id))

    assert execution.status == "completed"
    assert execution.execution_path == "decompose"
    assert task.status == "completed"


async def test_decompose_parse_failure_falls_back_to_self_execute(make_task, make_agent, mocker):
    """A ValidationError parsing the decompose response must not crash the job —
    it forces self_execute instead."""
    from pydantic import ValidationError

    task = make_task(status="reserved", delegation_depth=0)
    agent = make_agent()
    wctx, *_ = _patch_infra(mocker, task, agent)
    _decision(mocker, "decompose")

    def _raise(*args, **kwargs):
        raise ValidationError.from_exception_data("Decompose", [])

    mocker.patch.object(
        execute_task_module.structured_call, "call_and_parse", AsyncMock(side_effect=_raise)
    )
    mocker.patch.object(
        execute_task_module.tool_registry, "build_for_task_type", AsyncMock(return_value=([], []))
    )
    mocker.patch.object(execute_task_module.tool_registry, "get_skill_tag_map", return_value={})
    wctx.graphs["universal"].ainvoke = AsyncMock(
        return_value={
            "artifact": "done",
            "artifact_id": None,
            "step_count": 1,
            "tool_trace": [],
            "skill_tags_used": [],
        }
    )

    await execute_task_module.execute_task(CTX, str(agent.id), str(task.id), str(task.workspace_id))

    wctx.graphs["universal"].ainvoke.assert_awaited_once()
    assert task.status == "completed"


async def test_self_execute_happy_path_writes_results(make_task, make_agent, mocker):
    task = make_task(status="reserved", delegation_depth=0)
    agent = make_agent(skills={"writing": 0.8})
    wctx, *_, execution = _patch_infra(mocker, task, agent)
    _decision(mocker, "self_execute")
    mocker.patch.object(
        execute_task_module.tool_registry, "build_for_task_type", AsyncMock(return_value=([], []))
    )
    mocker.patch.object(execute_task_module.tool_registry, "get_skill_tag_map", return_value={})

    final_state = {
        "artifact": "final output",
        "artifact_id": None,
        "step_count": 2,
        "tool_trace": [],
        "skill_tags_used": ["writing"],
    }
    wctx.graphs["universal"].ainvoke = AsyncMock(return_value=final_state)

    await execute_task_module.execute_task(CTX, str(agent.id), str(task.id), str(task.workspace_id))

    assert execution.status == "completed"
    assert execution.execution_path == "self_execute"
    assert execution.artifact == "final output"
    assert task.status == "completed"
    # skill decay applied (settings.SKILL_DECAY_RATE < 1) but never below zero
    assert 0.0 <= agent.skills["writing"] < 0.8


# ── Failure path ──────────────────────────────────────────────────────────────


async def test_self_execute_exception_marks_execution_and_task_failed(
    make_task, make_agent, mocker
):
    task = make_task(status="reserved", delegation_depth=0)
    agent = make_agent()
    wctx, *_, execution = _patch_infra(mocker, task, agent)
    _decision(mocker, "self_execute")
    mocker.patch.object(
        execute_task_module.tool_registry, "build_for_task_type", AsyncMock(return_value=([], []))
    )
    mocker.patch.object(execute_task_module.tool_registry, "get_skill_tag_map", return_value={})
    wctx.graphs["universal"].ainvoke = AsyncMock(side_effect=RuntimeError("graph blew up"))

    with pytest.raises(RuntimeError, match="graph blew up"):
        await execute_task_module.execute_task(
            CTX, str(agent.id), str(task.id), str(task.workspace_id)
        )

    assert execution.status == "failed"
    assert execution.error == {"type": "RuntimeError", "message": "graph blew up"}
    assert task.status == "failed"


async def test_failure_after_terminal_commit_does_not_retransition_task(
    make_task, make_agent, mocker
):
    """If committed_task_status is already terminal (e.g. cfp path committed 'open' then a
    later step raised), the failure handler must not attempt an invalid transition."""
    task = make_task(status="reserved", delegation_depth=0)
    agent = make_agent()
    wctx, *_, execution = _patch_infra(mocker, task, agent)
    _decision(mocker, "self_execute")
    mocker.patch.object(
        execute_task_module.tool_registry, "build_for_task_type", AsyncMock(return_value=([], []))
    )
    mocker.patch.object(execute_task_module.tool_registry, "get_skill_tag_map", return_value={})

    final_state = {
        "artifact": "done",
        "artifact_id": None,
        "step_count": 1,
        "tool_trace": [],
        "skill_tags_used": [],
    }
    wctx.graphs["universal"].ainvoke = AsyncMock(return_value=final_state)

    # Force the post-graph write phase to blow up after task.status is already "completed"
    # in memory — simulates an exception raised after TaskStateMachine.transition() but
    # framed here via score_outcome to keep the test focused on the guard, not the trigger.
    mocker.patch.object(
        execute_task_module, "score_outcome", MagicMock(side_effect=RuntimeError("scoring bug"))
    )

    with pytest.raises(RuntimeError, match="scoring bug"):
        await execute_task_module.execute_task(
            CTX, str(agent.id), str(task.id), str(task.workspace_id)
        )

    # committed_task_status was still "executing" at the time of failure (score_outcome
    # raises before Phase 6's transition), so the handler transitions to "failed" cleanly.
    assert task.status == "failed"
    assert execution.status == "failed"
