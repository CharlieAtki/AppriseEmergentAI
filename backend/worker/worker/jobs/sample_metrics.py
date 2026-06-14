from __future__ import annotations

import logging
import math
from typing import Any

from sqlalchemy import select

from core.config import settings
from core.database import get_session
from core.models.agents import Agent
from core.models.observability import EmergenceEvent, WorkspaceMetricsSnapshot
from core.models.tenant import Workspace

logger = logging.getLogger(__name__)


async def sample_metrics(ctx: dict[str, Any]) -> None:
    """Cron job — runs every 15 seconds.

    For each active workspace: computes Gini coefficient over agent influence scores,
    specialisation index (mean pairwise skill vector distance), and detects hub agents.
    Writes WorkspaceMetricsSnapshot and EmergenceEvent rows to Postgres — those rows
    are the source of truth for any dashboard or reporting consumer.

    No LLM, no JobSpan, no bus dependency — pure arithmetic and DB writes.

    When a real-time dashboard consumer exists, add a WorkspaceMetricsUpdatedStreamEvent
    to core/eventing/events/stream_events.py and a WorkspaceStreamLogger that receives
    StreamPublishFn — following the same pattern as TaskStreamLogger. Do not call
    wctx.bus.publish() directly from this function.
    """
    async with get_session() as session:
        workspaces = (
            (await session.execute(select(Workspace).where(Workspace.status == "active")))
            .scalars()
            .all()
        )

        snapshots_written = 0
        for workspace in workspaces:
            agents = (
                (
                    await session.execute(
                        select(Agent).where(
                            Agent.workspace_id == workspace.id,
                            Agent.status == "active",
                        )
                    )
                )
                .scalars()
                .all()
            )

            if len(agents) < 2:
                continue

            influences = [a.influence or 0.0 for a in agents]
            skills_list = [a.skills or {} for a in agents]

            gini = _gini(influences)
            spec_index = _specialisation_index(skills_list)
            hub_agent = next(
                (
                    a
                    for a in agents
                    if (a.influence or 0.0) >= settings.intelligence.hub_influence_threshold
                ),
                None,
            )

            session.add(
                WorkspaceMetricsSnapshot(
                    workspace_id=workspace.id,
                    metrics={
                        "gini": gini,
                        "specialisation_index": spec_index,
                        "agent_count": len(agents),
                    },
                )
            )
            snapshots_written += 1

            if hub_agent:
                session.add(
                    EmergenceEvent(
                        workspace_id=workspace.id,
                        event_type="hub_detected",
                        gini_coefficient=gini,
                        hub_agent_id=hub_agent.id,
                    )
                )
                logger.info(
                    "emergence: hub agent %s detected in workspace %s (gini=%.3f)",
                    hub_agent.id,
                    workspace.id,
                    gini,
                )
        # Single commit for all workspaces on context manager exit

    if snapshots_written:
        logger.debug("sample_metrics: %d workspace snapshots written", snapshots_written)


def _gini(values: list[float]) -> float:
    """Gini coefficient in [0, 1] over a list of non-negative floats."""
    n = len(values)
    if n == 0:
        return 0.0
    sorted_vals = sorted(values)
    total = sum(sorted_vals)
    if total == 0.0:
        return 0.0
    cumulative = 0.0
    for i, v in enumerate(sorted_vals):
        cumulative += (2 * (i + 1) - n - 1) * v
    return cumulative / (n * total)


def _specialisation_index(skills_list: list[dict[str, float]]) -> float:
    """Mean pairwise cosine distance between agent skill vectors.

    Returns 0.0 (all identical) to 1.0 (completely orthogonal specialisations).
    """
    n = len(skills_list)
    if n < 2:
        return 0.0

    all_keys = set().union(*skills_list)
    if not all_keys:
        return 0.0

    vecs = [[skills.get(k, 0.0) for k in all_keys] for skills in skills_list]

    total_distance = 0.0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_similarity(vecs[i], vecs[j])
            total_distance += 1.0 - sim
            pairs += 1

    return total_distance / pairs if pairs else 0.0


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)
