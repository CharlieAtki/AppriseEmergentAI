from __future__ import annotations

from typing import TYPE_CHECKING

from core.agents.graphs.state import GraphState
from core.config import settings

if TYPE_CHECKING:
    from core.models.tasks import Task

_W_ARTIFACT = 0.60
_W_STEPS = 0.25
_W_TOOLS = 0.15


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_outcome(task: "Task", state: GraphState) -> float:
    """Return a deterministic quality score in [0.0, 1.0].

    Deterministic baseline only — no LLM calls. This value is written to
    ``TaskExecution.quality_score`` at execution time and is the authoritative
    quality signal for the reflection pipeline. No LLM score overwrites it.

    Components:
        artifact presence  0.60  — did the graph produce output?
        step efficiency    0.25  — did it finish well within the step limit?
        tool engagement    0.15  — did the agent use tools? (neutral if none used)
    """
    # Artifact: the primary success signal.
    artifact_score = 1.0 if state.get("artifact") else 0.1

    # Step efficiency: penalise runs that pushed near the limit.
    ratio = state["step_count"] / settings.intelligence.max_graph_steps
    step_score = _clamp01(1.0 - ratio * 0.6)

    # Tool engagement: 0.5 is neutral (simple tasks may not need tools).
    traces = state.get("tool_trace") or []
    if traces:
        tool_score = min(1.0, len(traces) / 3.0)
    else:
        tool_score = 0.5

    return _clamp01(
        _W_ARTIFACT * artifact_score
        + _W_STEPS * step_score
        + _W_TOOLS * tool_score
    )
