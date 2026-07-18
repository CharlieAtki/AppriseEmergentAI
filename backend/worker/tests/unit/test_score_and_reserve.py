"""Tests for worker.coordination.bidding.score_and_reserve.

This function is where bid scores turn into a committed task reservation.
The race-condition paths (SETNX win/loss, stale task status) are the most
likely source of silent double-execution bugs.

There is no minimum score to clear — the top-ranked candidate always wins if
the reservation race succeeds. attempt_reservation() claims two locks per win
(the task-level ``reservation:*`` key and the agent-level ``agent_busy:*``
key), so tests that assert on ``redis.set``/``redis.delete`` call sequences
account for both.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.repositories.task_repository import TaskRepository
from worker.coordination.bidding import score_and_reserve


def _agent(skills: Mapping[str, float], influence: float = 0.6) -> MagicMock:
    a = MagicMock()
    a.id = uuid.uuid4()
    a.skills = skills
    a.influence = influence
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
    task_repo, session, redis, arq_queue = _make_deps()
    result = await score_and_reserve(
        task_repo=task_repo,
        session=session,
        agents=[],
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        required_skills={},
        redis=redis,
        arq_queue=arq_queue,
    )
    assert result == 0
    arq_queue.enqueue_job.assert_not_called()
    redis.set.assert_not_called()


async def test_low_scoring_agent_still_wins_no_minimum_score(make_task):
    """There is no bid_score_threshold — an agent with zero matching skills and
    zero influence still wins and gets enqueued if it's the only candidate.
    This is the core invariant of the no-floor design: a task always gets
    assigned to whoever's available, rather than silently stalling forever."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    task = make_task(status="open", id=task_id, workspace_id=ws_id)

    redis.set = AsyncMock(return_value=b"OK")
    session.get = AsyncMock(return_value=task)

    agent = _agent(skills={}, influence=0.0)  # scores near-zero on skill+influence

    result = await score_and_reserve(
        task_repo=task_repo,
        session=session,
        agents=[agent],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"exotic_ml_skill": 1.0},
        redis=redis,
        arq_queue=arq_queue,
    )

    assert result == 1
    arq_queue.enqueue_job.assert_called_once()


# ── SETNX win — task still open ───────────────────────────────────────────────


async def test_setnx_win_task_open_enqueues_job(make_task):
    """Win the reservation and find the task still open → transition + enqueue."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    task = make_task(status="open", id=task_id, workspace_id=ws_id)

    redis.set = AsyncMock(return_value=b"OK")  # SETNX acquired (both locks)
    session.get = AsyncMock(return_value=task)

    events: list[str] = []
    session.commit = AsyncMock(side_effect=lambda: events.append("commit"))
    arq_queue.enqueue_job = AsyncMock(side_effect=lambda *a, **kw: events.append("enqueue"))

    agent = _agent(skills={"python": 1.0})

    await score_and_reserve(
        task_repo=task_repo,
        session=session,
        agents=[agent],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"python": 1.0},
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_called_once_with(
        "execute_task",
        agent_id=str(agent.id),
        task_id=str(task_id),
        workspace_id=str(ws_id),
    )
    # Neither lock is released on success
    redis.delete.assert_not_called()
    # Task status must be updated to "reserved"
    assert task.status == "reserved"
    # The reservation must be committed before the job is enqueued — otherwise
    # execute_task's independent session could observe the pre-reservation status.
    assert events == ["commit", "enqueue"]


# ── SETNX win — task status stale ─────────────────────────────────────────────


async def test_setnx_win_task_not_open_releases_reservation(make_task):
    """Win the SETNX but task is no longer "open" → release both locks, no enqueue."""
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
        session=session,
        agents=[agent],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"python": 1.0},
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_not_called()
    assert redis.delete.call_count == 2
    redis.delete.assert_any_call(f"reservation:{ws_id}:{task_id}")
    redis.delete.assert_any_call(f"agent_busy:{ws_id}:{agent.id}")


async def test_setnx_win_task_missing_releases_reservation():
    """Win the SETNX but the Task row is gone → release both locks, no enqueue."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    redis.set = AsyncMock(return_value=b"OK")
    session.get = AsyncMock(return_value=None)  # task deleted

    agent = _agent(skills={"python": 1.0})

    await score_and_reserve(
        task_repo=task_repo,
        session=session,
        agents=[agent],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"python": 1.0},
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_not_called()
    assert redis.delete.call_count == 2
    redis.delete.assert_any_call(f"reservation:{ws_id}:{task_id}")
    redis.delete.assert_any_call(f"agent_busy:{ws_id}:{agent.id}")


# ── SETNX loss ────────────────────────────────────────────────────────────────


async def test_setnx_loss_all_agents_no_enqueue():
    """All SETNX attempts fail → another worker won, no enqueue."""
    task_repo, session, redis, arq_queue = _make_deps()

    redis.set = AsyncMock(return_value=None)  # task-lock key already set

    agents = [_agent(skills={"python": 1.0}), _agent(skills={"python": 0.8})]

    await score_and_reserve(
        task_repo=task_repo,
        session=session,
        agents=agents,
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        required_skills={"python": 1.0},
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

    # agent1: task-lock attempt fails (1 call consumed).
    # agent2: task-lock succeeds, then agent-lock succeeds (2 calls consumed).
    redis.set = AsyncMock(side_effect=[None, b"OK", b"OK"])
    session.get = AsyncMock(return_value=task)

    # agent1 scores higher (sorted first), agent2 is fallback
    agent1 = _agent(skills={"python": 1.0}, influence=0.9)
    agent2 = _agent(skills={"python": 0.8}, influence=0.5)

    await score_and_reserve(
        task_repo=task_repo,
        session=session,
        agents=[agent1, agent2],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"python": 1.0},
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_called_once_with(
        "execute_task",
        agent_id=str(agent2.id),
        task_id=str(task_id),
        workspace_id=str(ws_id),
    )


# ── DB failure after SETNX win releases the reservation ────────────────────────


async def test_commit_failure_after_setnx_win_releases_reservation(make_task):
    """A transient DB failure between winning the SETNX and enqueueing must not
    leak either lock — otherwise the task is stuck "reserved" forever and the
    agent is stuck "busy" forever, and no other agent can ever win that slot.
    Regression test for the atomicity gap: the try/except used to wrap only
    enqueue_job, not TaskStateMachine.transition/save/commit."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    task = make_task(status="open", id=task_id, workspace_id=ws_id)

    redis.set = AsyncMock(return_value=b"OK")  # SETNX acquired (both locks)
    session.get = AsyncMock(return_value=task)
    session.commit = AsyncMock(side_effect=Exception("db unavailable"))

    agent = _agent(skills={"python": 1.0})

    with pytest.raises(Exception, match="db unavailable"):
        await score_and_reserve(
            task_repo=task_repo,
            session=session,
            agents=[agent],
            task_id=task_id,
            workspace_id=ws_id,
            required_skills={"python": 1.0},
            redis=redis,
            arq_queue=arq_queue,
        )

    assert redis.delete.call_count == 2
    redis.delete.assert_any_call(f"reservation:{ws_id}:{task_id}")
    redis.delete.assert_any_call(f"agent_busy:{ws_id}:{agent.id}")
    arq_queue.enqueue_job.assert_not_called()


async def test_enqueue_success_is_never_undone_by_a_later_step(make_task):
    """logger.info() runs after the protected try/except — it must never trigger
    a spurious lock deletion once enqueue_job has already succeeded."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    task = make_task(status="open", id=task_id, workspace_id=ws_id)

    redis.set = AsyncMock(return_value=b"OK")
    session.get = AsyncMock(return_value=task)

    agent = _agent(skills={"python": 1.0})

    await score_and_reserve(
        task_repo=task_repo,
        session=session,
        agents=[agent],
        task_id=task_id,
        workspace_id=ws_id,
        required_skills={"python": 1.0},
        redis=redis,
        arq_queue=arq_queue,
    )

    arq_queue.enqueue_job.assert_called_once()
    redis.delete.assert_not_called()


# ── Enqueue failure compensation ──────────────────────────────────────────────


async def test_enqueue_failure_releases_reservation(make_task):
    """If enqueue_job raises, both Redis locks must be deleted."""
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
            session=session,
            agents=[agent],
            task_id=task_id,
            workspace_id=ws_id,
            required_skills={"python": 1.0},
            redis=redis,
            arq_queue=arq_queue,
        )

    assert redis.delete.call_count == 2
    redis.delete.assert_any_call(f"reservation:{ws_id}:{task_id}")
    redis.delete.assert_any_call(f"agent_busy:{ws_id}:{agent.id}")


async def test_enqueue_failure_after_commit_reverts_task_to_open(make_task):
    """If enqueue_job fails after the "reserved" commit already succeeded, the
    task must be flipped back to "open" in a second commit — otherwise the
    bus-level Retry wrapper's next attempt would see task.status != "open"
    and bounce off it every time, leaving the task orphaned until the
    stale-reservation sweep (up to sweep_interval_minutes later) catches it."""
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
            session=session,
            agents=[agent],
            task_id=task_id,
            workspace_id=ws_id,
            required_skills={"python": 1.0},
            redis=redis,
            arq_queue=arq_queue,
        )

    assert task.status == "open"
    assert session.commit.await_count == 2


async def test_commit_failure_does_not_attempt_a_revert(make_task):
    """If session.commit() itself fails (the "reserved" transition never actually
    committed), there is nothing to revert — a second commit attempt would be
    pointless and could itself raise, masking the real error."""
    task_repo, session, redis, arq_queue = _make_deps()

    task_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    task = make_task(status="open", id=task_id, workspace_id=ws_id)

    redis.set = AsyncMock(return_value=b"OK")
    session.get = AsyncMock(return_value=task)
    session.commit = AsyncMock(side_effect=Exception("db unavailable"))

    agent = _agent(skills={"python": 1.0})

    with pytest.raises(Exception, match="db unavailable"):
        await score_and_reserve(
            task_repo=task_repo,
            session=session,
            agents=[agent],
            task_id=task_id,
            workspace_id=ws_id,
            required_skills={"python": 1.0},
            redis=redis,
            arq_queue=arq_queue,
        )

    assert session.commit.await_count == 1
    arq_queue.enqueue_job.assert_not_called()
