"""Tests for decompose_subtasks.

Regression guard for a fixed publish-before-commit bug: this function used to
take a TaskActivityLogger and fire task_logger.created(subtask) for every
subtask while still inside the caller's open transaction. If the caller's
commit then failed, that notification had already gone out for a subtask that
never actually persisted. The fix removed publishing from this function
entirely — the caller (worker/jobs/execute_task.py) now publishes after its
own session block closes. A function with no publish-shaped parameter cannot
reintroduce that bug, and the signature test below locks that in.
"""

from __future__ import annotations

import inspect
import uuid
from unittest.mock import AsyncMock

from core.coordination.decompose import SubtaskSpec, decompose_subtasks
from core.coordination.task_context import TaskContext


def _task_ctx(**overrides) -> TaskContext:
    defaults = dict(
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        parent_task_id=None,
        coordinator_agent_id=None,
        created_by_agent_id=None,
        delegation_depth=0,
    )
    defaults.update(overrides)
    return TaskContext(**defaults)


def _parent_task(**overrides):
    from types import SimpleNamespace

    defaults = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        task_type="general",
        required_skills={},
        difficulty=1.0,
        domain_tags={},
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _agent(**overrides):
    from types import SimpleNamespace

    defaults = dict(id=uuid.uuid4(), organisation_id=uuid.uuid4())
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_signature_has_no_publish_shaped_parameter():
    """Locks in the fix: nothing named/typed like a publisher can be passed here."""
    params = inspect.signature(decompose_subtasks).parameters
    assert "task_logger" not in params
    assert not any("publish" in name for name in params)


async def test_persists_a_subtask_per_spec_and_does_not_publish():
    task_repo = AsyncMock()
    parent = _parent_task()
    agent = _agent()
    specs: list[SubtaskSpec] = [{"title": "sub-1"}, {"title": "sub-2"}]

    created = await decompose_subtasks(agent, parent, specs, task_repo, task_ctx=_task_ctx())

    assert len(created) == 2
    assert task_repo.save.await_count == 2
    task_repo.flush.assert_awaited_once()


async def test_subtask_without_title_raises():
    task_repo = AsyncMock()
    parent = _parent_task()
    agent = _agent()

    try:
        await decompose_subtasks(agent, parent, [{}], task_repo, task_ctx=_task_ctx())
        raised = False
    except ValueError:
        raised = True
    assert raised


async def test_subtask_inherits_parent_defaults_when_spec_omits_fields():
    task_repo = AsyncMock()
    parent = _parent_task(task_type="research", difficulty=2.5, domain_tags={"x": 1})
    agent = _agent()

    created = await decompose_subtasks(
        agent, parent, [{"title": "sub"}], task_repo, task_ctx=_task_ctx()
    )

    subtask = created[0]
    assert subtask.task_type == "research"
    assert subtask.difficulty == 2.5
    assert subtask.domain_tags == {"x": 1}
    assert subtask.parent_task_id == parent.id


async def test_delegation_depth_increments_from_task_ctx():
    task_repo = AsyncMock()
    parent = _parent_task()
    agent = _agent()

    created = await decompose_subtasks(
        agent, parent, [{"title": "sub"}], task_repo, task_ctx=_task_ctx(delegation_depth=2)
    )

    assert created[0].delegation_depth == 3
