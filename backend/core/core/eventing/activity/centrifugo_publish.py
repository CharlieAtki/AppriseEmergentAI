"""PubSubPublishFn implementation backed by Centrifugo's HTTP API.

Exports a factory, not a bare module-level function or client — constructed
once at worker startup (worker/context.py) and injected at the same call
sites that used to receive wctx.redis.publish, matching JobSpan's own stated
principle that redis_publish is injected rather than resolved from a global
"so the span has no hidden global dependency and can be constructed in tests
with a mock callable." No other file (WorkspaceStreamLogger, JobSpan, the
event dataclasses) changes — PubSubPublishFn is the seam, and this is just a
new implementation of it.

Only ever constructed in worker/ — api/ never publishes dashboard or trace
events (its Centrifugo integration is read-only: connect/subscribe proxy auth
and the initial snapshot fetch), so wiring an httpx client into api/'s
lifespan for this would be dead weight.
"""

from __future__ import annotations

import json
import logging
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

    async def publish(channel: str, payload: str) -> None:
        # payload arrives as an already-json.dumps()'d string (WorkspaceStreamLogger's
        # own contract with PubSubPublishFn) — Centrifugo's publish API wants
        # structured JSON in `data`, not a pre-serialized string, so it must be
        # loaded back into a dict here rather than passed through directly.
        data = json.loads(payload)
        response = await client.post(
            f"{config.http_api_url}/publish",
            json={"channel": channel, "data": data},
            headers={"X-API-Key": config.http_api_key.get_secret_value()},
        )
        response.raise_for_status()

    return publish
