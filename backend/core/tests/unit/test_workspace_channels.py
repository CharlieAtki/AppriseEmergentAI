"""Tests for workspace-scoped channel naming — the single source of truth for
both the dashboard contract (channel_for) and the internal trace channel
(trace_channel_for), plus the inverse parser the Centrifugo subscribe proxy
uses to recover a workspace_id from a client's requested channel.
"""

from __future__ import annotations

import uuid

from core.eventing.activity.workspace_channels import (
    channel_for,
    trace_channel_for,
    workspace_id_from_events_channel,
)


def test_channel_for_shape():
    ws_id = uuid.uuid4()
    assert channel_for(ws_id) == f"workspace:{ws_id}:events"


def test_trace_channel_for_shape():
    ws_id = uuid.uuid4()
    assert trace_channel_for(ws_id) == f"workspace:{ws_id}:trace"


def test_channel_for_and_trace_channel_for_never_collide():
    ws_id = uuid.uuid4()
    assert channel_for(ws_id) != trace_channel_for(ws_id)


def test_workspace_id_from_events_channel_round_trips_channel_for():
    ws_id = uuid.uuid4()
    assert workspace_id_from_events_channel(channel_for(ws_id)) == ws_id


def test_workspace_id_from_events_channel_rejects_trace_channel():
    ws_id = uuid.uuid4()
    assert workspace_id_from_events_channel(trace_channel_for(ws_id)) is None


def test_workspace_id_from_events_channel_rejects_malformed_channel():
    assert workspace_id_from_events_channel("not-a-channel") is None
    assert workspace_id_from_events_channel("workspace:not-a-uuid:events") is None
    assert workspace_id_from_events_channel("other:12345:events") is None
