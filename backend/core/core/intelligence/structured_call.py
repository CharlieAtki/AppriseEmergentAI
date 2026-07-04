from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import ValidationError

from core.intelligence.call_types import CallType
from core.intelligence.llm_router import LLMRouter
from core.utils.retry import retry_async

logger = logging.getLogger(__name__)

_PARSE_RETRY_ATTEMPTS = 2  # one retry — a parse failure isn't rate-limited, no backoff needed


async def call_and_parse[T](
    llm_router: LLMRouter,
    call_type: CallType,
    messages: list[dict],
    parse: Callable[[str], T],
) -> T:
    """Call the LLM for `call_type`, parse the response, retrying once on a bad parse.

    Re-raises `ValidationError` if both attempts fail — the caller decides what "give up"
    means (force a different decision, propagate to a retry mechanism, etc.). Use this when
    no fallback value exists that doesn't fabricate success — see `run` otherwise.
    """

    async def _attempt() -> T:
        raw = await llm_router.complete(messages, call_type, json_mode=True)
        return parse(raw)

    return await retry_async(
        _attempt,
        is_retryable=lambda exc: isinstance(exc, ValidationError),
        max_attempts=_PARSE_RETRY_ATTEMPTS,
        backoff=0,
    )


async def run[T](
    llm_router: LLMRouter,
    call_type: CallType,
    messages: list[dict],
    parse: Callable[[str], T],
    fallback: T,
) -> T:
    """Call the LLM for `call_type`, parse the response, retrying once on a bad parse,
    and return `fallback` if both attempts fail.

    Only use `fallback` when accepting it can't cause the system to report false success —
    either it still results in real, verifiable work, or it's a true no-op that touches no
    completion/state signal. Use `call_and_parse` when no such value exists.

    Vendor-agnostic — dispatch goes through `LLMRouter`, not a specific SDK.
    """
    try:
        return await call_and_parse(llm_router, call_type, messages, parse)
    except ValidationError as exc:
        logger.warning("structured_call: %s parse failed, using fallback: %s", call_type, exc)
        return fallback
