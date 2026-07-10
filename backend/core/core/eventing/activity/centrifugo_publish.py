"""PubSubPublishFn implementation backed by Centrifugo's HTTP API.

Exports a factory, not a bare module-level function or client — constructed
once at worker startup (worker/context.py) and injected at the same call
sites that used to receive wctx.redis.publish, matching JobSpan's own stated
principle that publish is injected rather than resolved from a global "so the
span has no hidden global dependency and can be constructed in tests with a
mock callable." No other file (WorkspaceStreamLogger, JobSpan, the event
dataclasses) changes — PubSubPublishFn is the seam, and this is just a new
implementation of it.

This is the single place that turns a payload dict into wire JSON. Callers
(WorkspaceStreamLogger._emit(), JobSpan.emit()) hand over a plain dict and
never serialize it themselves — mirrors RedisBus.apublish(event), where the
transport owns serialization, not the producer. httpx's `json=` kwarg has no
hook for a custom `default=` encoder, so this builds the JSON body manually
via `json.dumps(..., default=str)` and posts it as raw `content=` — this is
what lets JobSpan.emit()'s deliberately open-ended tracing payloads carry a
stray UUID/datetime/Decimal without crashing, a responsibility this function
took over from JobSpan.emit() itself.

Only ever constructed in worker/ — api/ never publishes dashboard or trace
events (its Centrifugo integration is read-only: connect/subscribe proxy auth
and the initial snapshot fetch), so wiring an httpx client into api/'s
lifespan for this would be dead weight.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from core.config.vendors.centrifugo import CentrifugoConfig
    from core.eventing.activity.base import PubSubPublishFn

logger = logging.getLogger(__name__)


def make_centrifugo_publish(config: CentrifugoConfig, client: httpx.AsyncClient) -> PubSubPublishFn:
    """Build a PubSubPublishFn that POSTs to Centrifugo's /publish HTTP API.

    Does not swallow errors — WorkspaceStreamLogger._emit()'s existing
    try/except is what makes publishing best-effort; that boundary must stay
    exactly where it is today, not move into this transport implementation.
    """

    async def publish(channel: str, data: Mapping[str, object]) -> None:
        body = json.dumps({"channel": channel, "data": data}, default=str).encode("utf-8")
        response = await client.post(
            f"{config.http_api_url}/publish",
            content=body,
            headers={
                "X-API-Key": config.http_api_key.get_secret_value(),
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

    return publish
