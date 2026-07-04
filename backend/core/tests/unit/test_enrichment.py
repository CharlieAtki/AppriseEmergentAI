from __future__ import annotations

from unittest.mock import AsyncMock

from core.intelligence.enrichment import enrich


class TestEnrichRetry:
    async def test_retries_once_then_succeeds(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.side_effect = [
            "not json",
            '{"required_skills": {"python_coding": 0.9}, "difficulty": 3.0, '
            '"task_type": "coding", "domain_tags": {"backend": 0.8}}',
        ]

        # Title/description chosen to avoid matching any keyword rule, so rule-based
        # confidence stays below threshold and the LLM path is actually exercised.
        result = await enrich("zzz unmatched title", "zzz unmatched description", llm_router)

        assert result.confidence == 1.0
        assert result.required_skills == {"python_coding": 0.9}
        assert llm_router.complete.call_count == 2

    async def test_falls_back_to_rule_based_after_two_failures(self) -> None:
        llm_router = AsyncMock()
        llm_router.complete.return_value = "not json"

        result = await enrich("zzz unmatched title", "zzz unmatched description", llm_router)

        assert result.confidence == 0.0  # _FALLBACK rule-based result, unchanged
        assert llm_router.complete.call_count == 2
