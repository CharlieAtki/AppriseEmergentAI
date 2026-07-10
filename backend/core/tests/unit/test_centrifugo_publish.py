"""Contract tests for the Centrifugo-backed PubSubPublishFn implementation.

WorkspaceStreamLogger._emit() is the thing that makes publishing best-effort
(it swallows exceptions and logs) — these tests confirm make_centrifugo_publish()
itself does NOT swallow errors, so that guarantee stays exactly where it lives
today rather than silently duplicating (or losing) it in the transport layer.

This is also the one place in the seam that turns a payload dict into wire
JSON (see the module docstring on centrifugo_publish.py) — callers hand over
plain dicts, never pre-serialized strings, so these tests exercise that
dict-in, JSON-body-out contract directly.
"""

from __future__ import annotations

import datetime
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from core.config.vendors.centrifugo import CentrifugoConfig
from core.eventing.activity.centrifugo_publish import make_centrifugo_publish


def _make_client(response: MagicMock) -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    return client


def _ok_response() -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock()
    return response


async def test_publish_posts_to_configured_url_with_api_key():
    config = CentrifugoConfig(http_api_url="http://centrifugo:8000/api", http_api_key="secret-key")
    client = _make_client(_ok_response())
    publish = make_centrifugo_publish(config, client)

    await publish("workspace:abc:events", {"type": "task.completed"})

    client.post.assert_awaited_once()
    call = client.post.call_args
    assert call.args[0] == "http://centrifugo:8000/api/publish"
    assert call.kwargs["headers"]["X-API-Key"] == "secret-key"
    assert call.kwargs["headers"]["Content-Type"] == "application/json"


async def test_publish_serializes_dict_as_json_body():
    """publish() now owns dict -> wire-JSON serialization entirely — the caller
    hands over a plain dict, and the posted body must be the {channel, data}
    envelope, serialized exactly once, here."""
    config = CentrifugoConfig(http_api_url="http://centrifugo:8000/api", http_api_key="k")
    client = _make_client(_ok_response())
    publish = make_centrifugo_publish(config, client)

    await publish("workspace:abc:events", {"type": "task.completed", "quality_score": 0.9})

    body = json.loads(client.post.call_args.kwargs["content"])
    assert body == {
        "channel": "workspace:abc:events",
        "data": {"type": "task.completed", "quality_score": 0.9},
    }


async def test_publish_serializes_non_json_native_values_via_default_str():
    """JobSpan.emit()'s tracing payloads are deliberately open-ended and can
    carry a raw UUID/datetime — httpx's json= kwarg has no default= hook, so
    this function must build the body itself with default=str to avoid
    crashing on values that worked fine before this responsibility moved here."""
    config = CentrifugoConfig(http_api_url="http://centrifugo:8000/api", http_api_key="k")
    client = _make_client(_ok_response())
    publish = make_centrifugo_publish(config, client)

    agent_id = uuid.uuid4()
    ts = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

    await publish("trace:abc:events", {"agent_id": agent_id, "ts": ts})  # must not raise

    body = json.loads(client.post.call_args.kwargs["content"])
    assert body["data"]["agent_id"] == str(agent_id)
    assert body["data"]["ts"] == str(ts)


async def test_publish_raises_on_non_2xx_response():
    """Errors must propagate — the caller (WorkspaceStreamLogger._emit()) is what
    provides best-effort semantics; this function must not swallow anything
    itself, or that guarantee would silently duplicate/diverge."""
    config = CentrifugoConfig(http_api_url="http://centrifugo:8000/api", http_api_key="k")
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("boom", request=MagicMock(), response=MagicMock())
    )
    client = _make_client(response)
    publish = make_centrifugo_publish(config, client)

    with pytest.raises(httpx.HTTPStatusError):
        await publish("workspace:abc:events", {"type": "task.completed"})
