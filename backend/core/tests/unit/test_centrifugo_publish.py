"""Contract tests for the Centrifugo-backed PubSubPublishFn implementation.

WorkspaceStreamLogger._emit() is the thing that makes publishing best-effort
(it swallows exceptions and logs) — these tests confirm make_centrifugo_publish()
itself does NOT swallow errors, so that guarantee stays exactly where it lives
today rather than silently duplicating (or losing) it in the transport layer.
"""

from __future__ import annotations

import json
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

    await publish("workspace:abc:events", json.dumps({"type": "task.completed"}))

    client.post.assert_awaited_once()
    call = client.post.call_args
    assert call.args[0] == "http://centrifugo:8000/api/publish"
    assert call.kwargs["headers"]["X-API-Key"] == "secret-key"


async def test_publish_round_trips_json_string_back_into_a_dict():
    """WorkspaceStreamLogger hands publish() an already-json.dumps()'d string —
    Centrifugo's API wants structured JSON in `data`, so it must be loaded back
    into a dict, not passed through as a double-encoded string."""
    config = CentrifugoConfig(http_api_url="http://centrifugo:8000/api", http_api_key="k")
    client = _make_client(_ok_response())
    publish = make_centrifugo_publish(config, client)

    await publish(
        "workspace:abc:events", json.dumps({"type": "task.completed", "quality_score": 0.9})
    )

    body = client.post.call_args.kwargs["json"]
    assert body == {
        "channel": "workspace:abc:events",
        "data": {"type": "task.completed", "quality_score": 0.9},
    }


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
        await publish("workspace:abc:events", json.dumps({"type": "task.completed"}))
