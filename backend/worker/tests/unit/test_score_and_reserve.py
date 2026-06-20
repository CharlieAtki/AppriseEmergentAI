"""Tests for worker.coordination.bidding.score_and_reserve.

This function is where bid scores turn into a committed task reservation.
The race-condition paths (SETNX win/loss, stale task status) are the most
likely source of silent double-execution bugs.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.repositories.task_repository import TaskRepository
from worker.coordination.bidding import score_and_reserve


def _agent(skills: Mapping[str, float], active_tasks: int = 0, influence: float = 0.6) -> MagicMock:
    a = MagicMock()
    a.id = uuid.uuid4()
    a.skills = skills
    a.influence = influence
    a.personality = {}
    a.task_executions = [MagicMock(status="executing")] * active_tasks
    return a


def _make_deps():
    """Return (task_repo, session_mock, redis, arq_queue).

    task_repo wraps a real TaskRepository around the session mock so callers can
    configure session.get and session.execute to control what the repo returns —
    without mocking SQLAlchemy internals directly in score_and_reserve itself.
    """
    session = AsyncMock()
    task_repo = TaskRepository(session)
    redis = AsyncMock()
    arq_queue = AsyncMock()
    arq_queue.enqueue_job = AsyncMock()
    return task_repo, session, redis, arq_queue


# ── No candidates ─────────────────────────────────────────────────────────────


async def test_no_agents_returns_silently():
    task_repo, _session, redis, arq_queue = _make_deps()
    await score_and_reserve(
        task_repo=task_repo,
        agents=[],
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        required_skills={},
        domain_tags=None,
        redis=redis,
        arq_queue=arq_queue,
    )
    arq_queue.enqueue_job.assert_not_called()
    redis.set.assert_not_called()


async def test_all_below_threshold_no_enqueue():
    """Agent with zero matching skills scores below BID_SCORE_THRESHOLD (0.3)."""
    task_repo, _session, redis, arq_queue = _make_deps()
    # No skills, no influence, full queue → score ~ 0.025 (personality only)
    agent = _agent(skills={}, active_tasks=3, influence=0.0)

    await score_and_reserve(
        task_repo=task_repo,
        agents=[agent],
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        required_skills={"exotic_ml_skill": 1.0},
        domain_tags=None,
        redis=redis,
        arq_queue=arq_queue,
    )
    arq_queue.enqueue_job.assert_not_called()
    redis.set.assert_not_called()


# ── SETNX win — task still open ───────────────────────────────────────────────


async def test_setnx_win_task_open_enqueues_job(make_task):
    """Win the reservation and find the task still open → transition + enqueue."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    task = make_task(status="open", id=task_id, workspace_id=ws_id)

    redis.set = AsyncMock(return_value=b"OK")  # SETNX acquired
    session.get = AsyncMock(return_value=task)

    agent = _agent(skills={"python": 1.0})

    await score_and_reserve(
        task_repo=task_repo,
        agents=[agent],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"python": 1.0},
        domain_tags=None,
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_called_once_with(
        "execute_task",
        agent_id=str(agent.id),
        task_id=str(task_id),
        workspace_id=str(ws_id),
    )
    # Reservation key must NOT be deleted on success
    redis.delete.assert_not_called()
    # Task status must be updated to "reserved"
    assert task.status == "reserved"


# ── SETNX win — task status stale ─────────────────────────────────────────────


async def test_setnx_win_task_not_open_releases_reservation(make_task):
    """Win the SETNX but task is no longer "open" → release key, no enqueue."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    # Task already grabbed by another worker between score and reservation
    task = make_task(status="reserved", id=task_id, workspace_id=ws_id)

    redis.set = AsyncMock(return_value=b"OK")
    session.get = AsyncMock(return_value=task)

    agent = _agent(skills={"python": 1.0})

    await score_and_reserve(
        task_repo=task_repo,
        agents=[agent],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"python": 1.0},
        domain_tags=None,
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_not_called()
    redis.delete.assert_called_once_with(f"reservation:{ws_id}:{task_id}")


async def test_setnx_win_task_missing_releases_reservation():
    """Win the SETNX but the Task row is gone → release key, no enqueue."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    redis.set = AsyncMock(return_value=b"OK")
    session.get = AsyncMock(return_value=None)  # task deleted

    agent = _agent(skills={"python": 1.0})

    await score_and_reserve(
        task_repo=task_repo,
        agents=[agent],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"python": 1.0},
        domain_tags=None,
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_not_called()
    redis.delete.assert_called_once_with(f"reservation:{ws_id}:{task_id}")


# ── SETNX loss ────────────────────────────────────────────────────────────────


async def test_setnx_loss_all_agents_no_enqueue():
    """All SETNX attempts fail → another worker won, no enqueue."""
    task_repo, _session, redis, arq_queue = _make_deps()

    redis.set = AsyncMock(return_value=None)  # key already set

    agents = [_agent(skills={"python": 1.0}), _agent(skills={"python": 0.8})]

    await score_and_reserve(
        task_repo=task_repo,
        agents=agents,
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        required_skills={"python": 1.0},
        domain_tags=None,
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_not_called()


async def test_setnx_loss_on_first_win_on_second(make_task):
    """First agent loses SETNX; second agent wins and enqueues the job."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    task = make_task(status="open", id=task_id, workspace_id=ws_id)

    # First call → loss, second call → win
    redis.set = AsyncMock(side_effect=[None, b"OK"])
    session.get = AsyncMock(return_value=task)

    # agent1 scores higher (sorted first), agent2 is fallback
    agent1 = _agent(skills={"python": 1.0}, influence=0.9)
    agent2 = _agent(skills={"python": 0.8}, influence=0.5)

    await score_and_reserve(
        task_repo=task_repo,
        agents=[agent1, agent2],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"python": 1.0},
        domain_tags=None,
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_called_once_with(
        "execute_task",
        agent_id=str(agent2.id),
        task_id=str(task_id),
        workspace_id=str(ws_id),
    )


# ── Enqueue failure compensation ──────────────────────────────────────────────


async def test_enqueue_failure_releases_reservation(make_task):
    """If enqueue_job raises, the Redis reservation key must be deleted."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    task = make_task(status="open", id=task_id, workspace_id=ws_id)

    redis.set = AsyncMock(return_value=b"OK")
    session.get = AsyncMock(return_value=task)
    arq_queue.enqueue_job = AsyncMock(side_effect=RuntimeError("arq unavailable"))

    agent = _agent(skills={"python": 1.0})

    with pytest.raises(RuntimeError, match="arq unavailable"):
        await score_and_reserve(
            task_repo=task_repo,
            agents=[agent],
            task_id=task_id,
            workspace_id=ws_id,
            required_skills={"python": 1.0},
            domain_tags=None,
            redis=redis,
            arq_queue=arq_queue,
        )

    redis.delete.assert_called_once_with(f"reservation:{ws_id}:{task_id}")
