"""Tests for the Centrifugo proxy router's auth guard and boundary parsing.

No FastAPI TestClient here — this codebase's convention (see test_span.py,
test_centrifugo_proxy_service.py) is direct unit testing of the functions
themselves, not full ASGI app fixtures. require_centrifugo_proxy_secret() and
the boundary dataclasses are plain functions/classmethods, testable as such.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from api.deps import require_centrifugo_proxy_secret
from api.routers.centrifugo_proxy import CentrifugoConnectRequest, CentrifugoSubscribeRequest
from fastapi import HTTPException


def _make_request(headers: dict[str, str]) -> MagicMock:
    request = MagicMock()
    request.headers = headers
    return request


def test_require_centrifugo_proxy_secret_rejects_missing_header():
    request = _make_request({})
    with (
        patch(
            "api.deps.core_settings.centrifugo.proxy_secret.get_secret_value",
            return_value="the-real-secret",
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        require_centrifugo_proxy_secret(request)
    assert exc_info.value.status_code == 401


def test_require_centrifugo_proxy_secret_rejects_wrong_secret():
    request = _make_request({"X-Centrifugo-Proxy-Secret": "wrong"})
    with (
        patch(
            "api.deps.core_settings.centrifugo.proxy_secret.get_secret_value",
            return_value="the-real-secret",
        ),
        pytest.raises(HTTPException),
    ):
        require_centrifugo_proxy_secret(request)


def test_require_centrifugo_proxy_secret_accepts_matching_secret():
    request = _make_request({"X-Centrifugo-Proxy-Secret": "the-real-secret"})
    with patch(
        "api.deps.core_settings.centrifugo.proxy_secret.get_secret_value",
        return_value="the-real-secret",
    ):
        require_centrifugo_proxy_secret(request)  # must not raise


def test_require_centrifugo_proxy_secret_rejects_when_unconfigured():
    """An empty configured secret must never match an empty/missing header —
    otherwise an unconfigured deployment would silently accept everything."""
    request = _make_request({"X-Centrifugo-Proxy-Secret": ""})
    with (
        patch("api.deps.core_settings.centrifugo.proxy_secret.get_secret_value", return_value=""),
        pytest.raises(HTTPException),
    ):
        require_centrifugo_proxy_secret(request)


def test_connect_request_parses_clerk_token_from_data():
    """Field name is clerkToken (camelCase) — matches the frontend's getData()
    payload (useWorkspaceStream.ts), a JS-side ad hoc protocol, not one of this
    app's snake_case Pydantic schemas."""
    body = {"client": "abc", "data": {"clerkToken": "tok"}}
    parsed = CentrifugoConnectRequest.from_body(body)
    assert parsed.clerk_token == "tok"


def test_connect_request_missing_data_yields_none_token():
    parsed = CentrifugoConnectRequest.from_body({"client": "abc"})
    assert parsed.clerk_token is None


def test_subscribe_request_parses_org_id_from_forwarded_meta():
    org_id = uuid.uuid4()
    body = {"channel": "workspace:x:events", "meta": {"org_id": str(org_id)}}
    parsed = CentrifugoSubscribeRequest.from_body(body)
    assert parsed.org_id == org_id
    assert parsed.channel == "workspace:x:events"


def test_subscribe_request_missing_meta_yields_none_org_id():
    parsed = CentrifugoSubscribeRequest.from_body({"channel": "workspace:x:events"})
    assert parsed.org_id is None


def test_subscribe_request_malformed_org_id_yields_none_not_raise():
    parsed = CentrifugoSubscribeRequest.from_body(
        {"channel": "workspace:x:events", "meta": {"org_id": "not-a-uuid"}}
    )
    assert parsed.org_id is None
