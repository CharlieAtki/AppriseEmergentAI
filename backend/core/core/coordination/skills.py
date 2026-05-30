from __future__ import annotations


def apply_skill_delta(current: float, delta: float) -> float:
    """Apply a skill delta using logistic growth (diminishing returns).

    Implements the Notion spec: "A skill at 0.3 grows faster than a skill at 0.8."
    The same raw delta from the LLM produces a larger absolute change when the current
    skill is low, and a smaller change when it is already high.

    Two behaviours split by delta sign:

    Positive (growth):  new = current + delta * (1 - current)
        Growth tapers as skill approaches 1.0. A perfect agent finds it hard to improve
        further; a novice agent picks up the same delta more readily.

    Negative (penalty): new = current + delta * current
        Penalty tapers as skill approaches 0.0. An agent cannot lose skill they have
        not yet developed. A highly-skilled agent takes a proportionally larger hit for
        failure.

    Boundary behaviour:
        delta=+0.3, current=0.0 → 0.30  (full gain from zero)
        delta=+0.3, current=0.8 → 0.86  (diminished gain at high skill)
        delta=+0.3, current=1.0 → 1.00  (no overflow)
        delta=-0.2, current=1.0 → 0.80  (full penalty at high skill)
        delta=-0.2, current=0.3 → 0.24  (diminished penalty at low skill)
        delta=-0.2, current=0.0 → 0.00  (no underflow)
    """
    if delta >= 0.0:
        new = current + delta * (1.0 - current)
    else:
        new = current + delta * current
    return max(0.0, min(1.0, new))