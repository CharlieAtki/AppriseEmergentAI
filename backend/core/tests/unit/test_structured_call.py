from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from core.intelligence import structured_call
from core.intelligence.call_types import CallType
from pydantic import BaseModel


class _Response(BaseModel):
    value: str


def _parse(raw: str) -> _Response:
    return _Response.model_validate_json(raw)


class TestCallAndParse:
    async def test_returns_parsed_response_on_first_success(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.return_value = '{"value": "ok"}'

        result = await structured_call.call_and_parse(
            llm_router, CallType.EVALUATE, [{"role": "user", "content": "hi"}], _parse
        )

        assert result == _Response(value="ok")
        assert llm_router.complete.call_count == 1

    async def test_retries_once_then_succeeds(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.side_effect = ["not json", '{"value": "ok"}']

        result = await structured_call.call_and_parse(
            llm_router, CallType.EVALUATE, [{"role": "user", "content": "hi"}], _parse
        )

        assert result == _Response(value="ok")
        assert llm_router.complete.call_count == 2

    async def test_reraises_validation_error_after_two_failures(self) -> None:
        from pydantic import ValidationError

        llm_router = AsyncMock()
        llm_router.complete.return_value = "not json"

        with pytest.raises(ValidationError):
            await structured_call.call_and_parse(
                llm_router, CallType.EVALUATE, [{"role": "user", "content": "hi"}], _parse
            )

        assert llm_router.complete.call_count == 2

    async def test_does_not_swallow_unrelated_exceptions(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.return_value = '{"value": "ok"}'

        def _broken_parse(raw: str) -> _Response:
            raise RuntimeError("unrelated bug")

        with pytest.raises(RuntimeError):
            await structured_call.call_and_parse(
                llm_router, CallType.EVALUATE, [{"role": "user", "content": "hi"}], _broken_parse
            )

        assert llm_router.complete.call_count == 1


class TestStructuredCallRun:
    async def test_returns_parsed_response_on_success(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.return_value = '{"value": "ok"}'

        result = await structured_call.run(
            llm_router,
            CallType.EVALUATE,
            [{"role": "user", "content": "hi"}],
            _parse,
            fallback=_Response(value="fallback"),
        )

        assert result == _Response(value="ok")

    async def test_retries_once_before_using_fallback(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.side_effect = ["not json", '{"value": "ok"}']

        result = await structured_call.run(
            llm_router,
            CallType.EVALUATE,
            [{"role": "user", "content": "hi"}],
            _parse,
            fallback=_Response(value="fallback"),
        )

        assert result == _Response(value="ok")
        assert llm_router.complete.call_count == 2

    async def test_returns_fallback_on_malformed_json(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.return_value = "not json"

        result = await structured_call.run(
            llm_router,
            CallType.EVALUATE,
            [{"role": "user", "content": "hi"}],
            _parse,
            fallback=_Response(value="fallback"),
        )

        assert result == _Response(value="fallback")
        assert llm_router.complete.call_count == 2

    async def test_returns_fallback_on_schema_mismatch(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.return_value = '{"wrong_field": 1}'

        result = await structured_call.run(
            llm_router,
            CallType.EVALUATE,
            [{"role": "user", "content": "hi"}],
            _parse,
            fallback=_Response(value="fallback"),
        )

        assert result == _Response(value="fallback")

    async def test_logs_warning_on_parse_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        llm_router = AsyncMock()
        llm_router.complete.return_value = "not json"

        with caplog.at_level(logging.WARNING, logger="core.intelligence.structured_call"):
            await structured_call.run(
                llm_router,
                CallType.EVALUATE,
                [{"role": "user", "content": "hi"}],
                _parse,
                fallback=_Response(value="fallback"),
            )

        assert any("parse failed" in record.message for record in caplog.records)

    async def test_does_not_swallow_unrelated_exceptions(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.return_value = '{"value": "ok"}'

        def _broken_parse(raw: str) -> _Response:
            raise RuntimeError("unrelated bug")

        with pytest.raises(RuntimeError):
            await structured_call.run(
                llm_router,
                CallType.EVALUATE,
                [{"role": "user", "content": "hi"}],
                _broken_parse,
                fallback=_Response(value="fallback"),
            )
