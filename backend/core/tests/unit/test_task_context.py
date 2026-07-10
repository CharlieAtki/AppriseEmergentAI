"""Tests for TaskContext.from_task().

TaskContext is a pure value-object mapping from a Task ORM row — no I/O, no
logic beyond attribute copying. It's worth testing directly because
delegation_depth is the exact field execute_task.py's depth guard reads
(provenance.delegation_depth >= coord_cfg.max_delegation_depth); a mapping bug
here (e.g. copying the wrong attribute) would silently defeat that guard.
The guard's branching behaviour itself is covered separately in
worker/tests/unit/test_execute_task.py::test_depth_guard_forces_self_execute.
"""

from __future__ import annotations

import types
import uuid

from core.coordination.task_context import TaskContext


def _make_task(**overrides) -> types.SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        parent_task_id=None,
        coordinator_agent_id=None,
        created_by_agent_id=None,
        delegation_depth=0,
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def test_from_task_maps_every_field():
    task = _make_task(
        parent_task_id=uuid.uuid4(),
        coordinator_agent_id=uuid.uuid4(),
        created_by_agent_id=uuid.uuid4(),
        delegation_depth=3,
    )

    ctx = TaskContext.from_task(task)

    assert ctx.task_id == task.id
    assert ctx.workspace_id == task.workspace_id
    assert ctx.organisation_id == task.organisation_id
    assert ctx.parent_task_id == task.parent_task_id
    assert ctx.coordinator_agent_id == task.coordinator_agent_id
    assert ctx.created_by_agent_id == task.created_by_agent_id
    assert ctx.delegation_depth == task.delegation_depth


def test_from_task_preserves_root_task_nullable_fields():
    """A root task (no parent, no coordinator, no delegator) has all three
    nullable ancestry fields as None — these must round-trip as None, not
    coerce to a sentinel."""
    task = _make_task()

    ctx = TaskContext.from_task(task)

    assert ctx.parent_task_id is None
    assert ctx.coordinator_agent_id is None
    assert ctx.created_by_agent_id is None


def test_from_task_carries_delegation_depth_used_by_the_depth_guard():
    """delegation_depth is read verbatim by execute_task.py's depth guard
    (provenance.delegation_depth >= coord_cfg.max_delegation_depth) — this
    pins the mapping so a future field rename can't silently break the guard."""
    task = _make_task(delegation_depth=5)

    ctx = TaskContext.from_task(task)

    assert ctx.delegation_depth == 5


def test_task_context_is_frozen():
    ctx = TaskContext.from_task(_make_task())
    try:
        ctx.delegation_depth = 99  # type: ignore[misc]
        raised = False
    except AttributeError:
        raised = True
    assert raised, "TaskContext must be immutable"
