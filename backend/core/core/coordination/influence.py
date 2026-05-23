from __future__ import annotations


def compute_influence_ema(current: float | None, quality: float) -> float:
    """Blend a new quality signal into the running influence score via EMA.

    Influence is an exponential moving average of task quality scores. It
    reflects an agent's sustained performance over time and feeds directly into
    ContractNet bid scoring — higher influence makes an agent more competitive
    for future tasks.

    The EMA formula is: new = base + alpha * (quality - base)

    ``alpha`` (``settings.INFLUENCE_EMA_ALPHA``) controls how quickly new
    quality signals displace historical ones. A higher alpha makes the score
    more reactive; a lower alpha gives more weight to the agent's history.

    ``current=None`` is treated as 0.0 — the starting influence of a new agent
    with no task history.
    """
    from core.config import settings

    base = current if current is not None else 0.0
    return base + settings.INFLUENCE_EMA_ALPHA * (quality - base)
