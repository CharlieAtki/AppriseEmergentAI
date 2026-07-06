"""Redis Pub/Sub facade for live dashboard events.

This is the stable, external-facing event vocabulary consumed by the frontend's
WorkspaceEvent Zod union (frontend/src/hooks/workspace/useWorkspaceStream.ts) — a
different concern from JobSpan.emit()'s fine-grained tracing events, which
accumulate into TaskExecution.tool_trace for audit/debug replay. Renaming a
tracing event must never silently break the dashboard contract, so the two
never share a vocabulary.

Every method takes primitives only (uuid.UUID, float, Mapping) — never an ORM
object. Wire shaping is owned by the typed event classes in
core/eventing/events/workspace_stream_events.py, not built inline here as ad hoc
dict literals — this file only constructs the right event and publishes it.

channel_for() (re-exported here from workspace_channels.py, the actual single
source of truth for workspace-scoped channel naming) is imported by both the
publish side (this file) and the subscribe side (api/'s Centrifugo subscribe
proxy). It is deliberately not defined in this file — this file's vocabulary
is the frontend contract; trace_channel_for(), the sibling channel for
internal tracing events, is explicitly not part of that contract, so the two
names live together in workspace_channels.py instead of here.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING

from core.eventing.activity.workspace_channels import channel_for
from core.eventing.events.workspace_stream_events import (
    AgentSkillUpdatedEvent,
    EmergenceDetectedEvent,
    TaskCompletedEvent,
    TaskExecutingEvent,
    WorkspaceStreamEvent,
)

if TYPE_CHECKING:
    from core.eventing.activity.base import PubSubPublishFn

logger = logging.getLogger(__name__)

__all__ = ["WorkspaceStreamLogger", "channel_for"]


class WorkspaceStreamLogger:
    """Facade that publishes typed dashboard events. Never touch the publish transport directly.

    Construct with ``WorkspaceStreamLogger(wctx.centrifugo_publish)`` — either inline in a
    job function with no JobSpan (e.g. sample_metrics.py), or via ``JobSpan.stream``
    for jobs that already have a span.
    """

    def __init__(self, publish: PubSubPublishFn) -> None:
        self._publish = publish

    async def _emit(self, workspace_id: uuid.UUID, event: WorkspaceStreamEvent) -> None:
        """Best-effort — a dropped dashboard notification must never abort the
        caller's real workflow (task execution, reflection, metrics sampling).
        Centralised here rather than wrapped at each call site so every current
        and future publish is covered by one guarantee, not three-plus duplicated
        try/excepts that could drift or be forgotten at a new call site.
        """
        try:
            payload = event.to_payload()
            await self._publish(channel_for(workspace_id), json.dumps(payload))
        except Exception:
            logger.exception(
                "WorkspaceStreamLogger: failed to publish %s for workspace=%s",
                type(event).__name__,
                workspace_id,
            )

    async def task_executing(
        self, workspace_id: uuid.UUID, task_id: uuid.UUID, agent_id: uuid.UUID
    ) -> None:
        await self._emit(workspace_id, TaskExecutingEvent(task_id=task_id, agent_id=agent_id))

    async def task_completed(
        self,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
        agent_id: uuid.UUID,
        quality_score: float,
    ) -> None:
        await self._emit(
            workspace_id,
            TaskCompletedEvent(task_id=task_id, agent_id=agent_id, quality_score=quality_score),
        )

    async def skill_updated(
        self,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        skill_deltas: Mapping[str, float],
        new_influence: float,
    ) -> None:
        await self._emit(
            workspace_id,
            AgentSkillUpdatedEvent(
                agent_id=agent_id, skill_deltas=skill_deltas, new_influence=new_influence
            ),
        )

    async def emergence_detected(
        self, workspace_id: uuid.UUID, gini_coefficient: float, hub_agent_id: uuid.UUID
    ) -> None:
        await self._emit(
            workspace_id,
            EmergenceDetectedEvent(gini_coefficient=gini_coefficient, hub_agent_id=hub_agent_id),
        )
