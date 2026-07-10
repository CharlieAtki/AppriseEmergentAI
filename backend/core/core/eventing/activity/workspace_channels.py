"""Single source of truth for workspace-scoped channel naming.

Two distinct vocabularies share the `workspace:{id}` namespace but must never
share a channel:

``channel_for()`` — the stable, external-facing dashboard contract published by
    WorkspaceStreamLogger and consumed by the frontend's WorkspaceEvent Zod
    union. See workspace_stream_logger.py.

``trace_channel_for()`` — internal tracing events published by JobSpan.emit()
    (job.started, agent.executing, agent.scored, ...) that accumulate into
    TaskExecution.tool_trace for audit/debug replay. No frontend Zod schema
    will ever exist for these — they are not part of the dashboard contract.

Kept in one module, not defined ad hoc at each call site, specifically so a
future publisher never has to choose between hardcoding a channel string
(the bug this module fixes — JobSpan.emit() used to hand-build its channel
string directly) and reaching into an unrelated file to find one.
"""

from __future__ import annotations

import uuid


def channel_for(workspace_id: uuid.UUID) -> str:
    return f"workspace:{workspace_id}:events"


def trace_channel_for(workspace_id: uuid.UUID) -> str:
    return f"workspace:{workspace_id}:trace"


def workspace_id_from_events_channel(channel: str) -> uuid.UUID | None:
    """Inverse of channel_for() — used by the Centrifugo subscribe proxy to
    recover which workspace a client is asking to subscribe to. Deliberately
    only accepts the dashboard-contract channel shape (":events"), not the
    trace channel — nothing ever subscribes to trace events, and this refusal
    is what keeps that true rather than assumed."""
    prefix, sep, suffix = channel.partition(":")
    if prefix != "workspace" or not sep or not suffix.endswith(":events"):
        return None
    raw_id = suffix.removesuffix(":events")
    try:
        return uuid.UUID(raw_id)
    except ValueError:
        return None
