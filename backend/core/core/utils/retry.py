from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def is_retryable_http(exc: BaseException) -> bool:
    """True for transient HTTP errors safe to retry across any vendor SDK.

    Uses duck typing on status_code so this predicate works for Anthropic SDK,
    Qdrant client, raw httpx responses, and any future HTTP-based service without
    importing vendor-specific exception types.

    Retryable: 429 (rate-limited), 5xx (server failures), and network-level
    errors (connect timeout, remote hangup).
    Fatal: all other 4xx (auth, validation, not-found).
    """
    # Duck-type: any HTTP exception exposes status_code or response.status_code.
    raw = getattr(exc, "status_code", None)
    if raw is None:
        raw = getattr(getattr(exc, "response", None), "status_code", None)
    if raw is not None:
        try:
            return int(raw) in _RETRYABLE_STATUSES  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass

    # Network-level errors carry no status code — check via httpx base types.
    # httpx is a project-wide transport dependency, not a vendor SDK.
    try:
        import httpx
        return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError))
    except ImportError:
        return False


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    is_retryable: Callable[[BaseException], bool],
    max_attempts: int = 3,
    backoff: float = 1.0,
) -> T:
    """Retry any zero-argument async callable on transient errors.

    Sleeps backoff * 2**attempt seconds between attempts. Re-raises immediately
    on fatal errors or when all attempts are exhausted.

    Usage:
        from core.utils.retry import is_retryable_http, retry_async

        result = await retry_async(
            lambda: client.upsert(...),
            is_retryable=is_retryable_http,
        )
    """
    last_exc: Exception | None = None
    for attempt in range(max(1, max_attempts)):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if attempt == max_attempts - 1 or not is_retryable(exc):
                raise
            delay = backoff * 2 ** attempt
            logger.warning(
                "retry_async: attempt %d/%d failed (%s) — retrying in %.1fs",
                attempt + 1, max_attempts, type(exc).__name__, delay,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]  # unreachable in practice