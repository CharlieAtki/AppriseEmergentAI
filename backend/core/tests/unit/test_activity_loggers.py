"""Tests for TaskActivityLogger event publishing.

TaskActivityLogger's only job is translating a domain action into a correctly
shaped event and forwarding it through the injected publish callable. These
tests verify the shape (event type, snapshot contents, workspace_id) without
touching a real bus — publish is a bare AsyncMock.
"""

from __future__ import annotations

import types
import uuid
from unittest.mock import AsyncMock

from core.eventing.activity.task_logger import TaskActivityLogger
from core.eventing.events.task_events import (
    TaskCreatedEvent,
    TaskDeletedEvent,
    TaskSnapshot,
    TaskUpdatedEvent,
)


def _make_task(**overrides) -> types.SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        parent_task_id=None,
        coordinator_agent_id=None,
        created_by_agent_id=None,
        delegation_depth=0,
        title="test task",
        status="open",
        task_type="general",
        required_skills={},
        difficulty=1.0,
        domain_tags={},
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_snapshot(**overrides) -> TaskSnapshot:
    return TaskSnapshot.from_domain(_make_task(**overrides))


# ── created ───────────────────────────────────────────────────────────────────


async def test_created_publishes_task_created_event():
    publish = AsyncMock()
    logger = TaskActivityLogger(publish)
    task = _make_task()

    await logger.created(task)

    publish.assert_awaited_once()
    event = publish.call_args.args[0]
    assert isinstance(event, TaskCreatedEvent)
    assert event.workspace_id == task.workspace_id
    assert event.state.id == task.id
    assert event.state.status == "open"


# ── updated ───────────────────────────────────────────────────────────────────


async def test_updated_publishes_task_updated_event_with_before_and_after():
    publish = AsyncMock()
    logger = TaskActivityLogger(publish)

    before = _make_snapshot(status="open")
    after = _make_task(status="completed")

    await logger.updated(before, after)

    event = publish.call_args.args[0]
    assert isinstance(event, TaskUpdatedEvent)
    assert event.before is before
    assert event.state.status == "completed"
    assert event.workspace_id == after.workspace_id
    assert event.changed("status")


async def test_updated_forwards_synthetic_fields_onto_the_new_snapshot():
    """executing_agent_id, quality_score, execution_id, execution_path are not
    Task columns — they must be threaded through explicitly onto TaskSnapshot."""
    publish = AsyncMock()
    logger = TaskActivityLogger(publish)

    before = _make_snapshot(status="executing")
    after = _make_task(status="completed")
    agent_id = uuid.uuid4()
    exec_id = uuid.uuid4()

    await logger.updated(
        before,
        after,
        executing_agent_id=agent_id,
        quality_score=0.9,
        execution_id=exec_id,
        execution_path="self_execute",
    )

    event = publish.call_args.args[0]
    assert event.state.executing_agent_id == agent_id
    assert event.state.quality_score == 0.9
    assert event.state.execution_id == exec_id
    assert event.state.execution_path == "self_execute"
    # before snapshot must be untouched by the synthetic kwargs
    assert before.executing_agent_id is None


async def test_updated_no_status_change_changes_is_empty_for_status():
    publish = AsyncMock()
    logger = TaskActivityLogger(publish)

    before = _make_snapshot(status="open")
    after = _make_task(status="open")

    await logger.updated(before, after)

    event = publish.call_args.args[0]
    assert not event.changed("status")


# ── deleted ───────────────────────────────────────────────────────────────────


async def test_deleted_publishes_task_deleted_event():
    publish = AsyncMock()
    logger = TaskActivityLogger(publish)
    task = _make_task(status="open")

    await logger.deleted(task)

    publish.assert_awaited_once()
    event = publish.call_args.args[0]
    assert isinstance(event, TaskDeletedEvent)
    assert event.workspace_id == task.workspace_id
    assert event.state.id == task.id


# ── publish is called exactly once per method ──────────────────────────────────


async def test_each_method_publishes_exactly_one_event():
    publish = AsyncMock()
    logger = TaskActivityLogger(publish)
    task = _make_task()

    await logger.created(task)
    await logger.deleted(task)
    await logger.updated(_make_snapshot(), _make_task())

    assert publish.await_count == 3
