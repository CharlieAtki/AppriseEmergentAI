from __future__ import annotations

import pytest
from core.coordination.skills import apply_skill_delta, compute_delta_magnitude


class TestComputeDeltaMagnitude:
    def test_growth_when_quality_exceeds_current(self) -> None:
        delta = compute_delta_magnitude(quality_score=0.9, current_skill=0.5)
        assert delta > 0.0

    def test_decay_when_quality_below_current(self) -> None:
        delta = compute_delta_magnitude(quality_score=0.2, current_skill=0.7)
        assert delta < 0.0

    def test_zero_when_quality_equals_current(self) -> None:
        delta = compute_delta_magnitude(quality_score=0.5, current_skill=0.5)
        assert delta == pytest.approx(0.0)

    def test_custom_learning_rate_scales_delta(self) -> None:
        default = compute_delta_magnitude(quality_score=1.0, current_skill=0.0)
        double = compute_delta_magnitude(quality_score=1.0, current_skill=0.0, learning_rate=0.16)
        assert double == pytest.approx(default * 2)

    def test_formula(self) -> None:
        assert compute_delta_magnitude(0.8, 0.5, learning_rate=0.1) == pytest.approx(0.03)


class TestApplySkillDelta:
    def test_positive_delta_grows_skill(self) -> None:
        result = apply_skill_delta(current=0.3, delta=0.2)
        assert result > 0.3

    def test_negative_delta_shrinks_skill(self) -> None:
        result = apply_skill_delta(current=0.7, delta=-0.2)
        assert result < 0.7

    def test_growth_tapers_at_high_skill(self) -> None:
        gain_from_low = apply_skill_delta(0.1, 0.3) - 0.1
        gain_from_high = apply_skill_delta(0.9, 0.3) - 0.9
        assert gain_from_low > gain_from_high

    def test_penalty_tapers_at_low_skill(self) -> None:
        loss_from_high = 0.9 - apply_skill_delta(0.9, -0.2)
        loss_from_low = 0.1 - apply_skill_delta(0.1, -0.2)
        assert loss_from_high > loss_from_low

    def test_no_overflow_at_max_skill(self) -> None:
        assert apply_skill_delta(current=1.0, delta=0.5) == pytest.approx(1.0)

    def test_no_underflow_at_zero_skill(self) -> None:
        assert apply_skill_delta(current=0.0, delta=-0.5) == pytest.approx(0.0)

    def test_zero_delta_is_identity(self) -> None:
        assert apply_skill_delta(current=0.6, delta=0.0) == pytest.approx(0.6)

    def test_growth_formula(self) -> None:
        # new = current + delta * (1 - current) = 0.3 + 0.2 * 0.7 = 0.44
        assert apply_skill_delta(0.3, 0.2) == pytest.approx(0.44)

    def test_penalty_formula(self) -> None:
        # new = current + delta * current = 0.8 + (-0.2) * 0.8 = 0.64
        assert apply_skill_delta(0.8, -0.2) == pytest.approx(0.64)
