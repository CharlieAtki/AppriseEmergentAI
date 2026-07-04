from __future__ import annotations

from typing import Literal

from core.config import settings

InfluenceTier = Literal["high", "neutral", "low"]


def classify_influence(
    influence: float,
    *,
    hub_threshold: float = settings.intelligence.hub_influence_threshold,
    low_threshold: float = settings.intelligence.low_influence_threshold,
) -> InfluenceTier:
    """Bucket a raw influence score into the tier LLM prompts reason about.

    Shared with `sample_metrics.py`'s hub-agent detection so "high" always
    means the same threshold everywhere it's used.
    """
    if influence >= hub_threshold:
        return "high"
    if influence <= low_threshold:
        return "low"
    return "neutral"
