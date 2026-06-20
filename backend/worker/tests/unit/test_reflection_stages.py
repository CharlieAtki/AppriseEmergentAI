"""Tests for worker.reflection.stages — stage idempotency and guard logic.

The four stages (_stage_reflect, _stage_skills, _stage_rules, _stage_episodic)
each have idempotency guards designed to be safe on ARQ retry. Regressions here
cause double-applies (skills credited twice) or missing writes (rules lost on
Qdrant failure). We test the guards directly without running the full pipeline.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.intelligence.reflection.types import PipelineResult, ReflectContext
from worker.reflection.stages import _primary_domain, _stage_rules, _stage_skills

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_rctx(**kwargs) -> ReflectContext:
    defaults = dict(
        task_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        task_title="Test task",
        task_description=None,
        task_type="general",
        required_skills={"python": 1.0},
        difficulty=2.0,
        domain_tags={"python": 1.0},
        status="completed",
        artifact="done",
        error=None,
        tool_trace=(),
        heuristic_score=0.8,
        full_reflect=True,
        step_count=4,
        agent_skills={"python": 0.5},
    )
    return ReflectContext(**{**defaults, **kwargs})


def _make_result(**kwargs) -> PipelineResult:
    defaults = dict(
        skill_domains=[],
        new_skill_suggestions=[],
        rule=None,
        verdict=None,
        superseded_ids=None,
        stages_run=[],
        stages_failed=[],
    )
    return PipelineResult(**{**defaults, **kwargs})


def _make_span(session_factory=None):
    """Return a mock span whose .session() is the given async context manager factory."""
    span = MagicMock()
    span.emit = AsyncMock()
    if session_factory is not None:
        span.session = session_factory
    return span


# ── _primary_domain ───────────────────────────────────────────────────────────


def test_primary_domain_uses_task_type():
    rctx = _make_rctx(task_type="code")
    assert _primary_domain(rctx) == "code"


def test_primary_domain_falls_back_to_general():
    rctx = _make_rctx(task_type=None)
    assert _primary_domain(rctx) == "general"


# ── _stage_skills: empty domains → early return ───────────────────────────────


async def test_stage_skills_empty_domains_returns_without_db():
    rctx = _make_rctx()
    result = _make_result(skill_domains=[], new_skill_suggestions=[])

    span = _make_span()
    with patch("worker.reflection.stages.current_span", return_value=span):
        returned = await _stage_skills(rctx, result, AsyncMock(), AsyncMock())

    assert returned is result
    span.session.assert_not_called()  # MagicMock records .session call tracking


# ── _stage_skills: idempotency guard ─────────────────────────────────────────


async def test_stage_skills_idempotency_skip_when_snapshot_exists():
    """If a SkillSnapshot already exists for this execution_id, skip the stage."""
    rctx = _make_rctx()
    result = _make_result(skill_domains=["python"])

    existing_snapshot = MagicMock()  # truthy — snapshot exists

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=existing_snapshot)
    session.get = AsyncMock()  # must NOT be called

    @asynccontextmanager
    async def _session_cm():
        yield session

    span = _make_span(session_factory=_session_cm)
    with patch("worker.reflection.stages.current_span", return_value=span):
        await _stage_skills(rctx, result, AsyncMock(), AsyncMock())

    session.get.assert_not_called()


# ── _stage_skills: skill guard ────────────────────────────────────────────────


async def test_stage_skills_filters_out_of_required_set(caplog):
    """Skills named by LLM that are not in required_skills must be dropped."""
    rctx = _make_rctx(required_skills={"python": 1.0})
    result = _make_result(skill_domains=["python", "exotic_unlisted_skill"])

    agent = MagicMock()
    agent.id = rctx.agent_id
    agent.skills = {"python": 0.5}
    agent.organisation_id = rctx.organisation_id
    agent.workspace_id = rctx.workspace_id

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)  # no existing snapshot
    session.get = AsyncMock(return_value=agent)

    @asynccontextmanager
    async def _session_cm():
        yield session

    span = _make_span(session_factory=_session_cm)

    import logging

    with (
        patch("worker.reflection.stages.current_span", return_value=span),
        caplog.at_level(logging.WARNING, logger="worker.reflection.stages"),
    ):
        await _stage_skills(rctx, result, AsyncMock(), AsyncMock())

    # "exotic_unlisted_skill" must not be in the final agent.skills
    assert "exotic_unlisted_skill" not in agent.skills
    # Warning should be logged about the filtered skill
    assert "exotic_unlisted_skill" in caplog.text


async def test_stage_skills_seeds_new_skill_at_point_one():
    """New skill suggestions that are absent from the agent profile are seeded at 0.1."""
    rctx = _make_rctx(required_skills={"python": 1.0})
    result = _make_result(
        skill_domains=["python"],
        new_skill_suggestions=["rust"],
    )

    agent = MagicMock()
    agent.id = rctx.agent_id
    agent.skills = {"python": 0.5}
    agent.organisation_id = rctx.organisation_id
    agent.workspace_id = rctx.workspace_id

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=agent)

    @asynccontextmanager
    async def _session_cm():
        yield session

    span = _make_span(session_factory=_session_cm)
    with patch("worker.reflection.stages.current_span", return_value=span):
        await _stage_skills(rctx, result, AsyncMock(), AsyncMock())

    assert agent.skills.get("rust") == pytest.approx(0.1)


async def test_stage_skills_does_not_overwrite_existing_skill_with_seed():
    """Seeding must not overwrite a skill already present (even at 0.0)."""
    rctx = _make_rctx(required_skills={"python": 1.0})
    result = _make_result(
        skill_domains=["python"],
        new_skill_suggestions=["rust"],
    )

    agent = MagicMock()
    agent.id = rctx.agent_id
    agent.skills = {"python": 0.5, "rust": 0.0}  # rust exists at 0.0
    agent.organisation_id = rctx.organisation_id
    agent.workspace_id = rctx.workspace_id

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=agent)

    @asynccontextmanager
    async def _session_cm():
        yield session

    span = _make_span(session_factory=_session_cm)
    with patch("worker.reflection.stages.current_span", return_value=span):
        await _stage_skills(rctx, result, AsyncMock(), AsyncMock())

    # rust must remain at 0.0 — not overwritten by seed
    assert agent.skills["rust"] == pytest.approx(0.0)


# ── _stage_rules: early returns ───────────────────────────────────────────────


async def test_stage_rules_returns_early_when_no_rule():
    """No rule extracted → skip all DB and Qdrant writes."""
    rctx = _make_rctx()
    result = _make_result(rule=None)

    memory = AsyncMock()
    span = _make_span()

    with patch("worker.reflection.stages.current_span", return_value=span):
        returned = await _stage_rules(rctx, result, AsyncMock(), memory)

    assert returned is result
    memory.store_procedure.assert_not_called()


async def test_stage_rules_idempotency_both_writes_complete():
    """Existing log with vector_store_ref set → skip all three phases."""
    rctx = _make_rctx()
    result = _make_result(rule="Always use context managers.")

    existing_log = MagicMock()
    existing_log.vector_store_ref = "qdrant-point-id"  # both writes done

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=existing_log)

    @asynccontextmanager
    async def _session_cm():
        yield session

    span = _make_span(session_factory=_session_cm)
    memory = AsyncMock()

    with patch("worker.reflection.stages.current_span", return_value=span):
        await _stage_rules(rctx, result, AsyncMock(), memory)

    memory.store_procedure.assert_not_called()


# ── _stage_rules: full first-run path ────────────────────────────────────────


async def test_stage_rules_first_run_creates_log_and_writes_qdrant():
    """No existing log → Phase 1 (Postgres), Phase 2 (Qdrant), Phase 3 (stamp)."""
    rctx = _make_rctx()
    result = _make_result(rule="Always use context managers.", verdict="complements")

    point_id = "qdrant-point-abc"

    session1 = AsyncMock()
    session1.scalar = AsyncMock(return_value=None)  # no existing log (Phase 1)

    log_row = MagicMock()
    log_row.vector_store_ref = None
    session2 = AsyncMock()
    session2.get = AsyncMock(return_value=log_row)  # Phase 3

    sessions = iter([session1, session2])

    @asynccontextmanager
    async def _session_cm():
        yield next(sessions)

    span = _make_span(session_factory=_session_cm)
    memory = AsyncMock()
    memory.store_procedure = AsyncMock(return_value=point_id)

    with patch("worker.reflection.stages.current_span", return_value=span):
        await _stage_rules(rctx, result, AsyncMock(), memory)

    memory.store_procedure.assert_called_once()
    assert log_row.vector_store_ref == point_id


# ── _stage_rules: partial idempotency (Qdrant previously failed) ──────────────


async def test_stage_rules_retry_skips_phase1_reruns_phase2():
    """Existing log without vector_store_ref → skip Phase 1, retry Qdrant write."""
    rctx = _make_rctx()
    result = _make_result(rule="Retry pattern", verdict=None)

    existing_log_id = uuid.uuid4()
    existing_log = MagicMock()
    existing_log.id = existing_log_id
    existing_log.vector_store_ref = None  # Qdrant write previously failed

    point_id = "new-qdrant-point"

    session1 = AsyncMock()
    session1.scalar = AsyncMock(return_value=existing_log)

    log_row = MagicMock()
    log_row.vector_store_ref = None
    session2 = AsyncMock()
    session2.get = AsyncMock(return_value=log_row)

    sessions = iter([session1, session2])

    @asynccontextmanager
    async def _session_cm():
        yield next(sessions)

    span = _make_span(session_factory=_session_cm)
    memory = AsyncMock()
    memory.store_procedure = AsyncMock(return_value=point_id)

    with patch("worker.reflection.stages.current_span", return_value=span):
        await _stage_rules(rctx, result, AsyncMock(), memory)

    # Phase 2 must run
    memory.store_procedure.assert_called_once()
    # Phase 3 must stamp vector_store_ref
    assert log_row.vector_store_ref == point_id
    # Phase 1: session1.add must NOT have been called (no new log)
    session1.add.assert_not_called()
