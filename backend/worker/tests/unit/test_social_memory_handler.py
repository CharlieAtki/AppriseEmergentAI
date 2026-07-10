"""Tests for SocialMemoryHandler fan-out and failure isolation.

Social memory is soft state (the handler's own docstring says so — the next
task completion produces another observation) so the two invariants worth
locking in are: every active peer gets a write attempt, and one peer's Qdrant
failure must never prevent the others from being written or propagate out of
handle() (this handler is bound raw, without Retry — see worker/startup.py).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from core.eventing.events.stream_events import TaskCompletedStreamEvent
from worker.handlers.social_memory import SocialMemoryHandler


def _event(**overrides) -> TaskCompletedStreamEvent:
    defaults = dict(
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        completing_agent_id=uuid.uuid4(),
        quality_score=0.75,
        task_type="general",
    )
    defaults.update(overrides)
    return TaskCompletedStreamEvent(**defaults)


def _peer(agent_id=None) -> MagicMock:
    peer = MagicMock()
    peer.id = agent_id or uuid.uuid4()
    return peer


def _patch_session(mocker, peers: list[MagicMock]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = peers
    session.execute = AsyncMock(return_value=result)

    @asynccontextmanager
    async def _gs():
        yield session

    mocker.patch("worker.handlers.social_memory.get_session", _gs)
    return session


# ── Fan-out ───────────────────────────────────────────────────────────────────


async def test_writes_observation_to_every_active_peer(mocker):
    peers = [_peer(), _peer(), _peer()]
    _patch_session(mocker, peers)
    memory = MagicMock()
    memory.store_social = AsyncMock()

    handler = SocialMemoryHandler(memory=memory)
    await handler.handle(_event())

    assert memory.store_social.await_count == 3
    called_peer_ids = {call.args[0] for call in memory.store_social.call_args_list}
    assert called_peer_ids == {str(p.id) for p in peers}


async def test_observation_payload_shape(mocker):
    peer = _peer()
    _patch_session(mocker, [peer])
    memory = MagicMock()
    memory.store_social = AsyncMock()

    completing_agent_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    event = _event(
        completing_agent_id=completing_agent_id,
        workspace_id=workspace_id,
        quality_score=0.42,
        task_type="research",
    )

    handler = SocialMemoryHandler(memory=memory)
    await handler.handle(event)

    call = memory.store_social.call_args
    assert call.args[0] == str(peer.id)
    assert call.args[1] == str(workspace_id)
    observation = call.args[2]
    assert observation["observed_agent_id"] == str(completing_agent_id)
    assert observation["task_type"] == "research"
    assert observation["quality_score"] == 0.42
    assert str(completing_agent_id) in observation["text"]


async def test_no_active_peers_writes_nothing(mocker):
    _patch_session(mocker, [])
    memory = MagicMock()
    memory.store_social = AsyncMock()

    handler = SocialMemoryHandler(memory=memory)
    await handler.handle(_event())  # must not raise

    memory.store_social.assert_not_called()


# ── Failure isolation ─────────────────────────────────────────────────────────


async def test_one_peer_failure_does_not_block_the_others(mocker):
    peers = [_peer(), _peer(), _peer()]
    _patch_session(mocker, peers)
    memory = MagicMock()
    memory.store_social = AsyncMock(side_effect=[Exception("qdrant down"), None, None])

    handler = SocialMemoryHandler(memory=memory)
    await handler.handle(_event())  # must not raise despite the first failure

    assert memory.store_social.await_count == 3


async def test_all_peer_writes_failing_does_not_raise(mocker):
    peers = [_peer(), _peer()]
    _patch_session(mocker, peers)
    memory = MagicMock()
    memory.store_social = AsyncMock(side_effect=Exception("qdrant down"))

    handler = SocialMemoryHandler(memory=memory)
    await handler.handle(_event())  # must not raise

    assert memory.store_social.await_count == 2
