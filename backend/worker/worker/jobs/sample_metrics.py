"""ARQ cron job — samples workspace-level emergence metrics.

TODO: raw session calls (select(Workspace), session.add(WorkspaceMetricsSnapshot),
session.add(EmergenceEvent)) to be migrated to WorkspaceAdminRepository,
WorkspaceMetricsRepository, and EmergenceEventRepository when the cron job layer
is refactored.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass
from typing import Any

from core.database import get_session
from core.eventing.activity.workspace_stream_logger import WorkspaceStreamLogger
from core.intelligence.signals import classify_influence
from core.models.observability import (
    EmergenceEvent,
    WorkspaceMetricsPayload,
    WorkspaceMetricsSnapshot,
)
from core.models.tenant import Workspace
from core.repositories.agent_repository import AgentRepository
from sqlalchemy import select

from worker.context import get_worker_context

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectedEmergence:
    """One hub-agent detection collected during the loop, published only after
    the session block commits — see the comment at the call site below."""

    workspace_id: uuid.UUID
    gini: float
    hub_agent_id: uuid.UUID


async def sample_metrics(ctx: dict[str, Any]) -> None:
    """Cron job — runs every 15 seconds.

    For each active workspace: computes Gini coefficient over agent influence scores,
    specialisation index (mean pairwise skill vector distance), and detects hub agents.
    Writes WorkspaceMetricsSnapshot and EmergenceEvent rows to Postgres — those rows
    are the source of truth for any dashboard or reporting consumer.

    No LLM, no JobSpan — pure arithmetic and DB writes, plus a dashboard event fan-out.
    """
    wctx = get_worker_context()
    workspace_stream_logger = WorkspaceStreamLogger(wctx.redis.publish)
    # Collected during the loop, published only after the session block below commits —
    # no subscriber ever sees emergence.detected before the backing row is durable
    # (mirrors the create_task router's own commit-before-enqueue precedent).
    detected: list[DetectedEmergence] = []

    async with get_session() as session:
        workspaces = (
            (await session.execute(select(Workspace).where(Workspace.status == "active")))
            .scalars()
            .all()
        )

        agent_repo = AgentRepository(session)
        snapshots_written = 0
        for workspace in workspaces:
            agents = await agent_repo.get_all_active(workspace.id)

            if len(agents) < 2:
                continue

            influences = [a.influence or 0.0 for a in agents]
            skills_list = [a.skills or {} for a in agents]

            gini = _gini(influences)
            spec_index = _specialisation_index(skills_list)
            hub_agent = next(
                (a for a in agents if classify_influence(a.influence or 0.0) == "high"),
                None,
            )

            payload = WorkspaceMetricsPayload(
                gini=gini, specialisation_index=spec_index, agent_count=len(agents)
            )
            session.add(
                WorkspaceMetricsSnapshot(workspace_id=workspace.id, metrics=payload.to_dict())
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
                detected.append(
                    DetectedEmergence(
                        workspace_id=workspace.id, gini=gini, hub_agent_id=hub_agent.id
                    )
                )
                logger.info(
                    "emergence: hub agent %s detected in workspace %s (gini=%.3f)",
                    hub_agent.id,
                    workspace.id,
                    gini,
                )
        # Single commit for all workspaces on context manager exit

    # WorkspaceStreamLogger._emit() is itself best-effort (logs and swallows a
    # publish failure) — no try/except needed here.
    for detection in detected:
        await workspace_stream_logger.emergence_detected(
            detection.workspace_id, detection.gini, detection.hub_agent_id
        )

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
