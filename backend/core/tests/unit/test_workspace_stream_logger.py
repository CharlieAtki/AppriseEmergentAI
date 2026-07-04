"""Contract tests for WorkspaceStreamLogger — payload shapes must exactly match
the frontend's WorkspaceEvent Zod union (frontend/src/hooks/workspace/useWorkspaceStream.ts).
A drift here is silent on the Python side (json.dumps never fails) but breaks the
dashboard, since safeParse discards anything that doesn't match — these tests are
the guard against that.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

from core.eventing.activity.workspace_stream_logger import WorkspaceStreamLogger, channel_for


def _make_logger() -> tuple[WorkspaceStreamLogger, AsyncMock]:
    publish = AsyncMock()
    return WorkspaceStreamLogger(publish), publish


def test_channel_for_matches_worker_pubsub_channel():
    ws_id = uuid.uuid4()
    assert channel_for(ws_id) == f"workspace:{ws_id}:events"


async def test_task_executing_payload_shape():
    logger, publish = _make_logger()
    ws_id, task_id, agent_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    await logger.task_executing(ws_id, task_id, agent_id)

    channel, raw = publish.call_args.args
    assert channel == channel_for(ws_id)
    payload = json.loads(raw)
    assert payload == {
        "type": "task.executing",
        "task_id": str(task_id),
        "agent_id": str(agent_id),
    }


async def test_task_completed_payload_shape():
    logger, publish = _make_logger()
    ws_id, task_id, agent_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    await logger.task_completed(ws_id, task_id, agent_id, 0.87)

    payload = json.loads(publish.call_args.args[1])
    assert payload == {
        "type": "task.completed",
        "task_id": str(task_id),
        "agent_id": str(agent_id),
        "quality_score": 0.87,
    }


async def test_skill_updated_payload_shape():
    logger, publish = _make_logger()
    ws_id, agent_id = uuid.uuid4(), uuid.uuid4()

    await logger.skill_updated(ws_id, agent_id, {"python": 0.05}, 0.62)

    payload = json.loads(publish.call_args.args[1])
    assert payload == {
        "type": "agent.skill_updated",
        "agent_id": str(agent_id),
        "skill_deltas": {"python": 0.05},
        "new_influence": 0.62,
    }


async def test_emergence_detected_payload_shape():
    logger, publish = _make_logger()
    ws_id, hub_agent_id = uuid.uuid4(), uuid.uuid4()

    await logger.emergence_detected(ws_id, 0.42, hub_agent_id)

    payload = json.loads(publish.call_args.args[1])
    assert payload == {
        "type": "emergence.detected",
        "gini_coefficient": 0.42,
        "hub_agent_id": str(hub_agent_id),
    }


async def test_all_methods_publish_to_channel_for_given_workspace():
    """Every method must route through channel_for() — no hand-typed f-string drift."""
    logger, publish = _make_logger()
    ws_id = uuid.uuid4()

    await logger.task_executing(ws_id, uuid.uuid4(), uuid.uuid4())

    channel = publish.call_args.args[0]
    assert channel == channel_for(ws_id)


async def test_publish_failure_does_not_propagate():
    """A dropped Redis connection must not abort the caller's real workflow (task
    execution, reflection, metrics sampling) — this is what lets every call site
    await these methods directly with no try/except of its own."""
    publish = AsyncMock(side_effect=RuntimeError("redis down"))
    logger = WorkspaceStreamLogger(publish)

    await logger.task_completed(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), 0.5)  # must not raise
