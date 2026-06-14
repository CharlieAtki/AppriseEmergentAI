from __future__ import annotations

import pytest
from core.coordination.influence import compute_influence_ema


class TestComputeInfluenceEma:
    def test_cold_start_none_treated_as_zero(self) -> None:
        alpha = 0.15
        result = compute_influence_ema(current=None, quality=1.0, alpha=alpha)
        assert result == pytest.approx(alpha * 1.0)

    def test_cold_start_zero_quality(self) -> None:
        result = compute_influence_ema(current=None, quality=0.0, alpha=0.15)
        assert result == pytest.approx(0.0)

    def test_warm_start_known_values(self) -> None:
        # base=0.5, alpha=0.1, quality=1.0 → 0.5 + 0.1*(1.0-0.5) = 0.55
        result = compute_influence_ema(current=0.5, quality=1.0, alpha=0.1)
        assert result == pytest.approx(0.55)

    def test_warm_start_quality_below_current(self) -> None:
        # base=0.8, alpha=0.2, quality=0.0 → 0.8 + 0.2*(0.0-0.8) = 0.64
        result = compute_influence_ema(current=0.8, quality=0.0, alpha=0.2)
        assert result == pytest.approx(0.64)

    def test_custom_alpha_override(self) -> None:
        low_alpha = compute_influence_ema(current=0.0, quality=1.0, alpha=0.1)
        high_alpha = compute_influence_ema(current=0.0, quality=1.0, alpha=0.9)
        assert high_alpha > low_alpha

    def test_quality_equal_to_current_is_identity(self) -> None:
        result = compute_influence_ema(current=0.6, quality=0.6, alpha=0.3)
        assert result == pytest.approx(0.6)

    def test_default_alpha_comes_from_settings(self) -> None:
        from core.config import settings

        manual = compute_influence_ema(current=0.4, quality=0.8, alpha=settings.INFLUENCE_EMA_ALPHA)
        default = compute_influence_ema(current=0.4, quality=0.8)
        assert manual == pytest.approx(default)
