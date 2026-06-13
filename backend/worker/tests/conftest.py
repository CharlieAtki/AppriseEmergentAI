from __future__ import annotations

# Set required env vars before any core.config import resolves Settings().
# These must be module-level (not inside a fixture) so they're in place
# when pytest collects test files that import worker/core modules.
import os

os.environ.setdefault("DATABASE__URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("ANTHROPIC__API_KEY", "test-key-not-real")

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.eventing.events.task_events import TaskSnapshot, TaskUpdatedEvent


@pytest.fixture
def make_task():
    """Factory for lightweight Task-like stubs (no DB). Override fields via kwargs."""
    def _factory(status: str = "open", **kwargs) -> MagicMock:
        t = MagicMock()
        t.id = uuid.uuid4()
        t.workspace_id = uuid.uuid4()
        t.organisation_id = uuid.uuid4()
        t.parent_task_id = None
        t.coordinator_agent_id = None
        t.created_by_agent_id = None
        t.delegation_depth = 0
        t.title = "test task"
        t.status = status
        t.task_type = "general"
        t.required_skills = {}
        t.difficulty = 2.0
        t.domain_tags = {}
        t.external_ref = None
        t.deadline_at = None
        t.updated_at = None
        for k, v in kwargs.items():
            setattr(t, k, v)
        return t
    return _factory


@pytest.fixture
def make_agent():
    """Factory for lightweight Agent-like stubs (no DB)."""
    def _factory(skills: dict | None = None, influence: float = 0.5, **kwargs) -> MagicMock:
        a = MagicMock()
        a.id = uuid.uuid4()
        a.workspace_id = uuid.uuid4()
        a.organisation_id = uuid.uuid4()
        a.status = "active"
        a.skills = skills or {}
        a.influence = influence
        a.personality = {}
        a.task_executions = []
        for k, v in kwargs.items():
            setattr(a, k, v)
        return a
    return _factory


@pytest.fixture
def make_snapshot():
    """Factory for real TaskSnapshot instances with sensible defaults."""
    def _factory(**kwargs) -> TaskSnapshot:
        defaults: dict = dict(
            id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            organisation_id=uuid.uuid4(),
            parent_task_id=None,
            coordinator_agent_id=None,
            created_by_agent_id=None,
            delegation_depth=0,
            title="test",
            status="open",
            task_type="general",
            required_skills={},
            difficulty=1.0,
            domain_tags={},
            executing_agent_id=None,
            quality_score=None,
            execution_id=None,
            execution_path=None,
        )
        return TaskSnapshot(**{**defaults, **kwargs})
    return _factory


@pytest.fixture
def make_updated_event(make_snapshot):
    """Build a TaskUpdatedEvent from before/after status strings.

    ``changed("status")`` returns True when before_status != after_status.
    Pass the same string for both to get a no-op status event.
    """
    def _factory(
        before_status: str,
        after_status: str,
        **after_kwargs,
    ) -> TaskUpdatedEvent:
        # Allow callers to pin the workspace_id; otherwise generate a shared one.
        ws = after_kwargs.pop("workspace_id", uuid.uuid4())
        before = make_snapshot(status=before_status, workspace_id=ws)
        after = make_snapshot(status=after_status, workspace_id=ws, **after_kwargs)
        return TaskUpdatedEvent(state=after, before=before, workspace_id=ws)
    return _factory


@pytest.fixture
def arq_mock() -> AsyncMock:
    """Bare ARQ queue mock — configure enqueue_job side effects per test."""
    m = AsyncMock()
    m.enqueue_job = AsyncMock()
    return m


@pytest.fixture
def mock_session() -> AsyncMock:
    """Bare async mock session — configure return values per test."""
    return AsyncMock()


def make_session_patcher(module_path: str, session: AsyncMock, mocker):
    """Patch ``get_session`` in *module_path* to yield *session* as async CM."""
    @asynccontextmanager
    async def _ctx():
        yield session

    mocker.patch(f"{module_path}.get_session", _ctx)
    return session
