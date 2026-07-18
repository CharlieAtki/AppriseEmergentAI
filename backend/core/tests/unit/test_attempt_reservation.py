"""Tests for core.coordination.contract_net.attempt_reservation.

attempt_reservation claims two Redis SETNX locks per win: the task-level
``reservation:*`` key and the agent-level ``agent_busy:*`` key. The agent lock
is the actual correctness guarantee behind "one agent runs one task at a
time" — AgentRepository.get_active_for_bidding's query-level exclusion is
only an optimization on top of it. These tests exercise all three interleavings:
both locks free, task lock contested, and agent lock contested.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from core.coordination.contract_net import attempt_reservation


def _ids() -> tuple[str, str, str]:
    return str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


async def test_both_locks_free_succeeds():
    workspace_id, task_id, agent_id = _ids()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=b"OK")

    won = await attempt_reservation(redis, workspace_id, task_id, agent_id)

    assert won is True
    assert redis.set.call_count == 2
    redis.set.assert_any_call(f"reservation:{workspace_id}:{task_id}", agent_id, nx=True, ex=30)
    redis.set.assert_any_call(f"agent_busy:{workspace_id}:{agent_id}", task_id, nx=True, ex=30)
    redis.delete.assert_not_called()


async def test_task_lock_contested_never_attempts_agent_lock():
    """Another task already holds the reservation key — attempt_reservation
    must fail fast without ever attempting the agent-level lock."""
    workspace_id, task_id, agent_id = _ids()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=None)

    won = await attempt_reservation(redis, workspace_id, task_id, agent_id)

    assert won is False
    redis.set.assert_called_once()  # only the task-lock attempt
    redis.delete.assert_not_called()


async def test_agent_lock_contested_releases_task_lock():
    """Task lock wins, but a concurrent task already claimed this agent —
    attempt_reservation must roll back the task lock so another agent can
    still win the task this round."""
    workspace_id, task_id, agent_id = _ids()
    redis = AsyncMock()
    # First SETNX (task lock) succeeds, second (agent lock) fails.
    redis.set = AsyncMock(side_effect=[b"OK", None])

    won = await attempt_reservation(redis, workspace_id, task_id, agent_id)

    assert won is False
    assert redis.set.call_count == 2
    redis.delete.assert_called_once_with(f"reservation:{workspace_id}:{task_id}")
