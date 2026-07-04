from __future__ import annotations

from typing import Literal

from core.config import settings

InfluenceTier = Literal["high", "neutral", "low"]


def classify_influence(
    influence: float,
    *,
    hub_threshold: float | None = None,
    low_threshold: float | None = None,
) -> InfluenceTier:
    """Bucket a raw influence score into the tier LLM prompts reason about.

    Shared with `sample_metrics.py`'s hub-agent detection so "high" always
    means the same threshold everywhere it's used.
    """
    if hub_threshold is None:
        hub_threshold = settings.intelligence.hub_influence_threshold
    if low_threshold is None:
        low_threshold = settings.intelligence.low_influence_threshold
    if influence >= hub_threshold:
        return "high"
    if influence <= low_threshold:
        return "low"
    return "neutral"
