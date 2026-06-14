"""Tests for pure bid-scoring functions in core.coordination.contract_net.

All functions under test are pure (no I/O, no async). A regression here
silently routes tasks to the wrong agent — the functions are highest risk for
invisible logic drift.
"""

from __future__ import annotations

import pytest

from core.coordination.contract_net import (
    _capacity_factor,
    _influence_factor,
    _personality_fit,
    _seeded_jitter,
    _skill_match,
    compute_bid_score,
)

# ── _skill_match ────────────────────────────────────────────────────────────


def test_skill_match_perfect_overlap():
    """Agent fully covers all required skills → 1.0."""
    score = _skill_match(
        agent_skills={"python": 1.0, "ml": 1.0},
        required_skills={"python": 1.0, "ml": 1.0},
    )
    assert score == pytest.approx(1.0)


def test_skill_match_no_required_skills():
    """No required skills → neutral 0.5 (not zero — task has no constraint)."""
    assert _skill_match({"python": 1.0}, {}) == 0.5


def test_skill_match_zero_weight_required():
    """All required skill weights are zero → neutral 0.5."""
    assert _skill_match({"python": 1.0}, {"python": 0.0}) == 0.5


def test_skill_match_missing_skills():
    """Agent has none of the required skills → 0.0."""
    score = _skill_match(
        agent_skills={},
        required_skills={"python": 1.0, "ml": 0.5},
    )
    assert score == pytest.approx(0.0)


def test_skill_match_partial_coverage():
    """Partial skill overlap → weighted proportion."""
    # python weight=1.0 (agent=1.0), ml weight=1.0 (agent=0.0) → 0.5
    score = _skill_match(
        agent_skills={"python": 1.0},
        required_skills={"python": 1.0, "ml": 1.0},
    )
    assert score == pytest.approx(0.5)


def test_skill_match_clamped_above_one():
    """Agent skill value > 1.0 is clamped to 1.0 in the weighted sum."""
    score = _skill_match(
        agent_skills={"python": 5.0},  # raw value exceeds 1.0
        required_skills={"python": 1.0},
    )
    assert score == pytest.approx(1.0)


# ── _capacity_factor ─────────────────────────────────────────────────────────


def test_capacity_factor_idle():
    """Zero active tasks → full capacity (1.0)."""
    assert _capacity_factor(active_tasks=0, max_parallel=3) == pytest.approx(1.0)


def test_capacity_factor_full():
    """Active tasks == max_parallel → zero capacity."""
    assert _capacity_factor(active_tasks=3, max_parallel=3) == pytest.approx(0.0)


def test_capacity_factor_clamped_at_zero():
    """Active tasks > max_parallel → clamped to 0.0, not negative."""
    assert _capacity_factor(active_tasks=5, max_parallel=3) == pytest.approx(0.0)


def test_capacity_factor_zero_max():
    """max_parallel=0 → always 0.0 (guard against division by zero)."""
    assert _capacity_factor(active_tasks=0, max_parallel=0) == pytest.approx(0.0)


def test_capacity_factor_partial():
    """1 of 3 active → 2/3 capacity."""
    assert _capacity_factor(active_tasks=1, max_parallel=3) == pytest.approx(2 / 3)


# ── _influence_factor ─────────────────────────────────────────────────────────


def test_influence_factor_zero():
    """Influence = 0.0 → factor = 0.0 (no influence yet)."""
    assert _influence_factor(influence=0.0, k=2.0) == pytest.approx(0.0)


def test_influence_factor_saturates():
    """Very high influence → factor is clamped to 1.0 before exponential.

    _influence_factor(x, k) = 1 - exp(-k * clamp01(x))
    At influence=100.0, clamp01 caps to 1.0 → 1 - exp(-2.0) ≈ 0.865.
    This is the maximum possible value for k=2.0 — not close to 1.0.
    """
    factor = _influence_factor(influence=100.0, k=2.0)
    assert factor <= 1.0
    assert factor > 0.85


def test_influence_factor_clamps_above_one():
    """Influence > 1.0 is clamped to 1.0 before applying exponential."""
    f1 = _influence_factor(influence=1.0, k=2.0)
    f2 = _influence_factor(influence=10.0, k=2.0)
    assert f1 == pytest.approx(f2)


def test_influence_factor_monotone():
    """Higher influence → higher factor (monotone increasing up to clamp)."""
    assert _influence_factor(0.2, 2.0) < _influence_factor(0.5, 2.0)
    assert _influence_factor(0.5, 2.0) < _influence_factor(0.9, 2.0)


# ── _personality_fit ──────────────────────────────────────────────────────────


def test_personality_fit_no_personality():
    """No agent personality → neutral 0.5."""
    assert _personality_fit(agent_personality=None, task_domain_tags={"research": 1.0}) == 0.5


def test_personality_fit_no_tags():
    """No task domain tags → neutral 0.5."""
    assert _personality_fit(agent_personality={"research": 1.0}, task_domain_tags=None) == 0.5


def test_personality_fit_perfect_match():
    """Identical personality and domain → cosine similarity = 1.0 → fit = 1.0."""
    fit = _personality_fit(
        agent_personality={"research": 1.0},
        task_domain_tags={"research": 1.0},
    )
    assert fit == pytest.approx(1.0)


def test_personality_fit_orthogonal():
    """Completely different keys → cosine similarity = 0.0 → fit = 0.5."""
    fit = _personality_fit(
        agent_personality={"research": 1.0},
        task_domain_tags={"coding": 1.0},
    )
    assert fit == pytest.approx(0.5)


# ── _seeded_jitter ────────────────────────────────────────────────────────────


def test_seeded_jitter_deterministic():
    """Same (task_id, agent_id) always produces the same jitter."""
    j1 = _seeded_jitter("task-abc", "agent-xyz")
    j2 = _seeded_jitter("task-abc", "agent-xyz")
    assert j1 == j2


def test_seeded_jitter_in_range():
    """Jitter value is always within ±0.01."""
    for i in range(20):
        j = _seeded_jitter(f"task-{i}", f"agent-{i}")
        assert -0.01 <= j <= 0.01


def test_seeded_jitter_varies_by_input():
    """Different inputs should (typically) produce different jitter values."""
    values = {_seeded_jitter(f"task-{i}", "agent-0") for i in range(10)}
    assert len(values) > 1


# ── compute_bid_score (integration of sub-functions) ─────────────────────────


def test_compute_bid_score_above_zero():
    """Competent agent with matching skills scores well above zero."""
    score = compute_bid_score(
        agent_skills={"python": 0.9},
        agent_influence=0.7,
        agent_active_tasks=0,
        required_skills={"python": 1.0},
        add_jitter=False,
    )
    assert score > 0.5


def test_compute_bid_score_clamped():
    """Output is always in [0, 1] even with extreme inputs."""
    score = compute_bid_score(
        agent_skills={"python": 10.0},
        agent_influence=100.0,
        agent_active_tasks=0,
        required_skills={"python": 1.0},
        add_jitter=False,
    )
    assert 0.0 <= score <= 1.0


def test_compute_bid_score_no_skills_no_capacity():
    """Agent with no matching skills and full queue scores very low."""
    score = compute_bid_score(
        agent_skills={},
        agent_influence=0.0,
        agent_active_tasks=3,  # BID_MAX_PARALLEL_TASKS default = 3
        required_skills={"python": 1.0},
        add_jitter=False,
        max_parallel=3,
    )
    # skill=0, capacity=0, influence=0, personality=0.5 → w_personality * 0.5 = 0.025
    assert score < 0.1


def test_compute_bid_score_weighted_sum():
    """Manual calculation matches output with known inputs and no jitter."""
    # With defaults: w_skill=0.6, w_capacity=0.2, w_influence=0.15, w_personality=0.05
    # skill_match=1.0, capacity=1.0, influence_factor=0 (influence=0), personality=0.5
    expected = 0.60 * 1.0 + 0.20 * 1.0 + 0.15 * 0.0 + 0.05 * 0.5
    score = compute_bid_score(
        agent_skills={"python": 1.0},
        agent_influence=0.0,
        agent_active_tasks=0,
        required_skills={"python": 1.0},
        add_jitter=False,
        influence_k=2.0,
        max_parallel=3,
    )
    assert score == pytest.approx(expected)
