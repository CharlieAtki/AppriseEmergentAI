from __future__ import annotations

from core.agents.graphs.state import GraphState
from core.config import settings

# NOTE: Phase 2 replacement point.
# Deterministic proxy: artifact presence (60%), step efficiency (25%), tool engagement (15%).
# Replace body with LLM-as-judge scoring in Phase 2. Interface (state -> float) must remain stable.

_W_ARTIFACT = 0.60
_W_STEPS = 0.25
_W_TOOLS = 0.15


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_outcome(state: GraphState) -> float:
    """Return a deterministic quality score in [0.0, 1.0].

    Deterministic baseline only — no LLM calls. This value is written to
    ``TaskExecution.quality_score`` at execution time and is the authoritative
    quality signal for the reflection pipeline.

    Components:
        artifact presence  0.60  — did the graph produce text output or a stored artifact?
        step efficiency    0.25  — did it finish well within the step limit?
        tool engagement    0.15  — did the agent use tools? (neutral if none used)
    """
    artifact_score = 1.0 if (state.get("artifact") or state.get("artifact_id")) else 0.1

    ratio = state["step_count"] / settings.intelligence.max_graph_steps
    step_score = _clamp01(1.0 - ratio * 0.6)

    traces = state.get("tool_trace") or []
    tool_score = min(1.0, len(traces) / 3.0) if traces else 0.5

    return _clamp01(_W_ARTIFACT * artifact_score + _W_STEPS * step_score + _W_TOOLS * tool_score)
