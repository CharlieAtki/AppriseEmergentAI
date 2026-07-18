"""Tests for pure bid-scoring functions in core.coordination.contract_net.

All functions under test are pure (no I/O, no async). A regression here
silently routes tasks to the wrong agent — the functions are highest risk for
invisible logic drift.

There is no capacity/concurrency term here: compute_bid_score is only ever
called against agents already known to be idle (AgentRepository.get_active_for_bidding
excludes busy agents at the query level, and contract_net.attempt_reservation's
agent-level Redis lock is the actual correctness guarantee) — an agent with any
active task is never a scoring candidate in the first place.
"""

from __future__ import annotations

import pytest
from core.coordination.contract_net import (
    _influence_factor,
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


# ── compute_bid_score (integration of sub-functions) ─────────────────────────


def test_compute_bid_score_above_zero():
    """Competent agent with matching skills scores well above zero."""
    score = compute_bid_score(
        agent_skills={"python": 0.9},
        agent_influence=0.7,
        required_skills={"python": 1.0},
    )
    assert score > 0.5


def test_compute_bid_score_clamped():
    """Output is always in [0, 1] even with extreme inputs."""
    score = compute_bid_score(
        agent_skills={"python": 10.0},
        agent_influence=100.0,
        required_skills={"python": 1.0},
    )
    assert 0.0 <= score <= 1.0


def test_compute_bid_score_no_matching_skills():
    """Agent with none of the required skills and no influence scores zero."""
    score = compute_bid_score(
        agent_skills={},
        agent_influence=0.0,
        required_skills={"python": 1.0},
    )
    assert score == pytest.approx(0.0)


def test_compute_bid_score_weighted_sum():
    """Manual calculation matches output with known inputs."""
    # With defaults: w_skill=0.80, w_influence=0.20
    # skill_match=1.0, influence_factor=0 (influence=0)
    expected = 0.80 * 1.0 + 0.20 * 0.0
    score = compute_bid_score(
        agent_skills={"python": 1.0},
        agent_influence=0.0,
        required_skills={"python": 1.0},
        influence_k=2.0,
    )
    assert score == pytest.approx(expected)
