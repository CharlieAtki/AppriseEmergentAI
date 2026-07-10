"""Tests for the composable EventHandler wrappers: Retry, Filtering, Timeout,
SyncToAsync.

These wrappers compose error-handling policy at the bus.bind() registration
site rather than inside handler bodies. Each test verifies the wrapper's
contract in isolation, using a minimal fake handler rather than any real
domain handler — the wrappers are generic over EventHandler[E] and must work
regardless of what they wrap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest
from core.eventing.bus.handlers import Filtering, Retry, SyncToAsync, Timeout

# ── Fakes ───────────────────────────────────────────────────────────────────────


@dataclass
class _AsyncTracking:
    """Minimal EventHandler — records every event it handles."""

    calls: list[object] = field(default_factory=list)
    raise_times: int = 0  # number of leading calls that raise before succeeding
    exc_factory: type[Exception] = RuntimeError

    async def handle(self, event: object) -> None:
        if len(self.calls) < self.raise_times:
            self.calls.append(event)
            raise self.exc_factory("boom")
        self.calls.append(event)


@dataclass
class _SyncTracking:
    """Minimal SyncEventHandler — records every event it handles."""

    calls: list[object] = field(default_factory=list)

    def handle(self, event: object) -> None:
        self.calls.append(event)


@dataclass
class _SlowHandler:
    seconds: float

    async def handle(self, event: object) -> None:
        import asyncio

        await asyncio.sleep(self.seconds)


# ── SyncToAsync ───────────────────────────────────────────────────────────────


async def test_sync_to_async_runs_sync_handler():
    inner = _SyncTracking()
    wrapped = SyncToAsync(inner)

    await wrapped.handle("event-1")

    assert inner.calls == ["event-1"]


def test_sync_to_async_repr_names_wrapped_class():
    assert repr(SyncToAsync(_SyncTracking())) == "SyncToAsync(_SyncTracking)"


# ── Retry ─────────────────────────────────────────────────────────────────────


async def test_retry_succeeds_first_attempt_no_retry():
    inner = _AsyncTracking(raise_times=0)
    wrapped = Retry(inner, max_attempts=3, backoff=0.001)

    await wrapped.handle("event-1")

    assert len(inner.calls) == 1


async def test_retry_retries_transient_failure_then_succeeds():
    inner = _AsyncTracking(raise_times=2)
    wrapped = Retry(inner, max_attempts=3, backoff=0.001)

    await wrapped.handle("event-1")

    # Two failed attempts + one successful attempt = 3 calls to handle().
    assert len(inner.calls) == 3


async def test_retry_exhausts_attempts_and_reraises():
    inner = _AsyncTracking(raise_times=5)
    wrapped = Retry(inner, max_attempts=3, backoff=0.001)

    with pytest.raises(RuntimeError):
        await wrapped.handle("event-1")

    assert len(inner.calls) == 3


async def test_retry_fatal_on_skips_retry_immediately():
    inner = _AsyncTracking(raise_times=5, exc_factory=ValueError)
    wrapped = Retry(
        inner,
        max_attempts=3,
        retry_on=(Exception,),
        fatal_on=(ValueError,),
        backoff=0.001,
    )

    with pytest.raises(ValueError):
        await wrapped.handle("event-1")

    # fatal_on wins over retry_on — no retry, single attempt.
    assert len(inner.calls) == 1


async def test_retry_only_retries_matching_exception_types():
    """An exception outside retry_on propagates immediately, no retry."""
    inner = _AsyncTracking(raise_times=5, exc_factory=KeyError)
    wrapped = Retry(inner, max_attempts=3, retry_on=(ValueError,), backoff=0.001)

    with pytest.raises(KeyError):
        await wrapped.handle("event-1")

    assert len(inner.calls) == 1


def test_retry_repr_includes_max_attempts():
    assert "max=5" in repr(Retry(_AsyncTracking(), max_attempts=5))


# ── Filtering ─────────────────────────────────────────────────────────────────


async def test_filtering_runs_handler_when_predicate_true():
    inner = _AsyncTracking()
    wrapped = Filtering(inner, predicate=lambda e: True)

    await wrapped.handle("event-1")

    assert inner.calls == ["event-1"]


async def test_filtering_skips_handler_when_predicate_false():
    inner = _AsyncTracking()
    wrapped = Filtering(inner, predicate=lambda e: False)

    await wrapped.handle("event-1")

    assert inner.calls == []


async def test_filtering_predicate_receives_the_event():
    predicate = MagicMock(return_value=False)
    wrapped = Filtering(_AsyncTracking(), predicate=predicate)

    await wrapped.handle("event-1")

    predicate.assert_called_once_with("event-1")


# ── Timeout ───────────────────────────────────────────────────────────────────


async def test_timeout_completes_within_budget():
    inner = _AsyncTracking()
    wrapped = Timeout(inner, seconds=1.0)

    await wrapped.handle("event-1")

    assert inner.calls == ["event-1"]


async def test_timeout_raises_when_handler_exceeds_budget():
    wrapped = Timeout(_SlowHandler(seconds=0.2), seconds=0.01)

    with pytest.raises(TimeoutError):
        await wrapped.handle("event-1")


def test_timeout_repr_includes_seconds():
    assert "seconds=30" in repr(Timeout(_AsyncTracking(), seconds=30))
