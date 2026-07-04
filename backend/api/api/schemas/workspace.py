from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from core.models.enums import WorkspaceStatus
from pydantic import BaseModel

from api.schemas.agent import AgentResponse

__all__ = [
    "CreateWorkspaceRequest",
    "StreamTicketResponse",
    "UpdateWorkspaceRequest",
    "WorkspaceMetricsResponse",
    "WorkspaceResponse",
    "WorkspaceStatus",
    "WorkspaceStreamInitEvent",
]


class CreateWorkspaceRequest(BaseModel):
    name: str
    config: dict[str, Any] | None = None


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    status: WorkspaceStatus | None = None
    result_webhook_url: str | None = None
    webhook_secret: str | None = None
    config: dict[str, Any] | None = None


class WorkspaceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    status: WorkspaceStatus
    result_webhook_url: str | None
    created_at: datetime | None
    agent_count: int = 0


class StreamTicketResponse(BaseModel):
    model_config = {"from_attributes": True}

    ticket: str


class WorkspaceMetricsResponse(BaseModel):
    """The routine, periodic Workspace Metrics Snapshot — distinct from an
    Emergence Event (a discrete "hub agent detected" occurrence). See
    docs/backend/CONTEXT.md."""

    model_config = {"from_attributes": True}

    gini: float
    specialisation_index: float
    agent_count: int
    recorded_at: datetime


class WorkspaceStreamInitEvent(BaseModel):
    """Typed envelope for the WS 'init' message (GET /workspaces/{id}/stream).

    WebSocket routes aren't OpenAPI-covered, so there's no response_model to
    validate a send_json payload the way HTTP routes get for free — this model is
    what stands in for that on the WS path. The frontend still needs its own Zod
    schema (WorkspaceEvent's WorkspaceInitEvent variant) since Orval can't generate
    one for a non-REST message; this is what keeps the Python side honest that the
    dict actually sent matches the documented shape, rather than a hand-built dict
    drifting from it silently.
    """

    type: Literal["init"] = "init"
    agents: list[AgentResponse]
    metrics: WorkspaceMetricsResponse | None
