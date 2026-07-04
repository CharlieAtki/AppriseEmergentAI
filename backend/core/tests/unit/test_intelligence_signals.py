from __future__ import annotations

from core.intelligence.signals import classify_influence


class TestClassifyInfluence:
    def test_at_hub_threshold_is_high(self) -> None:
        assert classify_influence(0.7, hub_threshold=0.7, low_threshold=0.2) == "high"

    def test_above_hub_threshold_is_high(self) -> None:
        assert classify_influence(0.9, hub_threshold=0.7, low_threshold=0.2) == "high"

    def test_below_hub_threshold_is_neutral(self) -> None:
        assert classify_influence(0.69, hub_threshold=0.7, low_threshold=0.2) == "neutral"

    def test_at_low_threshold_is_low(self) -> None:
        assert classify_influence(0.2, hub_threshold=0.7, low_threshold=0.2) == "low"

    def test_below_low_threshold_is_low(self) -> None:
        assert classify_influence(0.0, hub_threshold=0.7, low_threshold=0.2) == "low"

    def test_between_thresholds_is_neutral(self) -> None:
        assert classify_influence(0.5, hub_threshold=0.7, low_threshold=0.2) == "neutral"

    def test_defaults_come_from_settings(self) -> None:
        from core.config import settings

        manual = classify_influence(
            0.8,
            hub_threshold=settings.intelligence.hub_influence_threshold,
            low_threshold=settings.intelligence.low_influence_threshold,
        )
        default = classify_influence(0.8)
        assert manual == default
