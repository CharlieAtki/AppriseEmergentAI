from __future__ import annotations


def compute_delta_magnitude(
    quality_score: float,
    current_skill: float,
    learning_rate: float = 0.08,
) -> float:
    """Compute how much a skill should change based on execution quality.

    Positive when quality_score > current_skill (agent outperformed its current level);
    negative when below. Pass the result to apply_skill_delta() to apply logistic
    growth bounds.

    Never ask the LLM for float deltas — this is the only source of delta magnitude
    in the reflection pipeline.
    """
    return learning_rate * (quality_score - current_skill)


def apply_skill_delta(current: float, delta: float) -> float:
    """Apply a skill delta using logistic growth (diminishing returns).

    Implements the Notion spec: "A skill at 0.3 grows faster than a skill at 0.8."
    The same raw delta (from ``compute_delta_magnitude``) produces a larger absolute
    change when the current skill is low, and a smaller change when it is already high.

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
