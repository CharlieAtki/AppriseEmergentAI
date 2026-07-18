"""Property-based tests for the pure functions in core/coordination/.

Complements the example-based tests in test_bid_scoring.py / test_influence.py /
test_skills.py — those pin specific input/output pairs, these assert invariants
that must hold across the whole input space (bounds, monotonicity, determinism).
"""

from __future__ import annotations

import random

from core.coordination.contract_net import break_ties, compute_bid_score
from core.coordination.influence import compute_influence_ema
from core.coordination.skills import apply_skill_delta, compute_delta_magnitude
from hypothesis import given
from hypothesis import strategies as st

unit_float = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
weight = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
skill_map = st.dictionaries(st.text(min_size=1, max_size=8), unit_float, min_size=0, max_size=5)


class TestComputeBidScoreProperties:
    @given(
        agent_skills=skill_map,
        agent_influence=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False),
        required_skills=skill_map,
        w_skill=weight,
        w_influence=weight,
    )
    def test_score_always_within_unit_interval(
        self, agent_skills, agent_influence, required_skills, w_skill, w_influence
    ) -> None:
        score = compute_bid_score(
            agent_skills=agent_skills,
            agent_influence=agent_influence,
            required_skills=required_skills,
            w_skill=w_skill,
            w_influence=w_influence,
        )
        assert 0.0 <= score <= 1.0

    @given(
        agent_skills=skill_map,
        agent_influence=unit_float,
        required_skills=skill_map,
    )
    def test_deterministic_for_identical_inputs(
        self, agent_skills, agent_influence, required_skills
    ) -> None:
        kwargs = dict(
            agent_skills=agent_skills,
            agent_influence=agent_influence,
            required_skills=required_skills,
        )
        assert compute_bid_score(**kwargs) == compute_bid_score(**kwargs)


class TestBreakTiesProperties:
    @given(
        scores=st.lists(unit_float, min_size=0, max_size=8),
        seed=st.integers(min_value=0, max_value=10_000),
    )
    def test_deterministic_for_same_seed(self, scores, seed) -> None:
        scored = [(i, score) for i, score in enumerate(scores)]
        result_1 = break_ties(list(scored), rng=random.Random(seed))
        result_2 = break_ties(list(scored), rng=random.Random(seed))
        assert result_1 == result_2

    @given(
        scores=st.lists(unit_float, min_size=0, max_size=8),
        seed=st.integers(min_value=0, max_value=10_000),
    )
    def test_result_is_descending_by_score(self, scores, seed) -> None:
        scored = [(i, score) for i, score in enumerate(scores)]
        result = break_ties(list(scored), rng=random.Random(seed))
        result_scores = [score for _, score in result]
        assert result_scores == sorted(result_scores, reverse=True)

    @given(
        scores=st.lists(unit_float, min_size=0, max_size=8),
        seed=st.integers(min_value=0, max_value=10_000),
    )
    def test_does_not_mutate_input(self, scores, seed) -> None:
        scored = [(i, score) for i, score in enumerate(scores)]
        original = list(scored)
        break_ties(scored, rng=random.Random(seed))
        assert scored == original


class TestComputeInfluenceEmaProperties:
    @given(current=unit_float, quality=unit_float, alpha=unit_float)
    def test_result_bounded_by_current_and_quality(self, current, quality, alpha) -> None:
        result = compute_influence_ema(current=current, quality=quality, alpha=alpha)
        lo, hi = min(current, quality), max(current, quality)
        assert lo - 1e-9 <= result <= hi + 1e-9

    @given(quality=unit_float, alpha=unit_float)
    def test_cold_start_never_exceeds_quality(self, quality, alpha) -> None:
        # current=None is treated as base=0.0, so the EMA can only move toward
        # (never past) quality.
        result = compute_influence_ema(current=None, quality=quality, alpha=alpha)
        assert 0.0 - 1e-9 <= result <= quality + 1e-9


class TestSkillDeltaProperties:
    @given(
        current=unit_float,
        quality=unit_float,
        learning_rate=st.floats(min_value=0.0, max_value=1.0),
    )
    def test_apply_skill_delta_stays_within_unit_interval(
        self, current, quality, learning_rate
    ) -> None:
        delta = compute_delta_magnitude(quality, current, learning_rate)
        new_skill = apply_skill_delta(current, delta)
        assert 0.0 <= new_skill <= 1.0

    @given(current=unit_float, delta=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False))
    def test_zero_delta_is_identity(self, current, delta) -> None:
        if delta == 0.0:
            assert apply_skill_delta(current, 0.0) == current
