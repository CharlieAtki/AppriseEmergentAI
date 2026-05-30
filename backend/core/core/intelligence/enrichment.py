from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.intelligence.llm_router import LLMRouter

from core.intelligence.call_types import CallType
from core.intelligence.prompts import enrich as _enrich_prompt

_CONFIDENCE_THRESHOLD = 0.85


@dataclass(frozen=True)
class EnrichmentOverrides:
    """Caller-supplied values that bypass or override enrichment output.

    When all three fields are set, the enrichment pipeline is skipped entirely.
    Any subset merges on top of the enrichment result — caller values win.
    """
    task_type: str | None = None
    required_skills: dict[str, float] | None = None
    difficulty: float | None = None


# ToDo: Need to look through this to check quality - is this correct
@dataclass(frozen=True)
class EnrichmentResult:
    required_skills: dict[str, float]
    difficulty: float
    task_type: str
    domain_tags: dict[str, float]
    confidence: float  # 0.0–1.0; >= 0.85 skips LLM escalation


_RULES: list[dict] = [
    {
        "task_type": "coding",
        "keywords": [
            "implement", "build", "fix", "debug", "refactor", "write code",
            "function", "api", "endpoint", "class", "module",
        ],
        "skills": {"coding": 0.9, "testing": 0.4},
        "base_difficulty": 2.5,
        "domains": {"software": 0.9},
        "confidence": 0.9,
    },
    {
        "task_type": "research",
        "keywords": [
            "research", "investigate", "analyse", "analyze", "review",
            "summarise", "summarize", "compare", "evaluate",
        ],
        "skills": {"research": 0.8, "reporting": 0.5},
        "base_difficulty": 2.0,
        "domains": {"research": 0.8},
        "confidence": 0.88,
    },
    {
        "task_type": "writing",
        "keywords": [
            "write", "draft", "compose", "document", "report",
            "blog", "article", "essay", "copy",
        ],
        "skills": {"writing": 0.9, "research": 0.3},
        "base_difficulty": 1.5,
        "domains": {"content": 0.8},
        "confidence": 0.9,
    },
    {
        "task_type": "analysis",
        "keywords": [
            "analyse", "analyze", "data", "metrics", "statistics",
            "model", "forecast", "predict", "dashboard", "chart",
        ],
        "skills": {"data_analysis": 0.9, "reporting": 0.4},
        "base_difficulty": 2.5,
        "domains": {"data": 0.9},
        "confidence": 0.87,
    },
]

_FALLBACK = EnrichmentResult(
    required_skills={"general": 0.5},
    difficulty=2.0,
    task_type="general",
    domain_tags={"general": 0.5},
    confidence=0.0,
)


def enrich_rule_based(title: str, description: str | None) -> EnrichmentResult:
    """Classify a task using keyword rules. Returns confidence=0.0 when no rule matches."""
    text = (title + " " + (description or "")).lower()
    for rule in _RULES:
        if any(kw in text for kw in rule["keywords"]):
            return EnrichmentResult(
                required_skills=rule["skills"],
                difficulty=rule["base_difficulty"],
                task_type=rule["task_type"],
                domain_tags=rule["domains"],
                confidence=rule["confidence"],
            )
    return _FALLBACK


async def enrich(
    title: str,
    description: str | None,
    llm_router: LLMRouter,
    overrides: EnrichmentOverrides | None = None,
) -> EnrichmentResult:
    """Run the full enrichment pipeline and return a resolved EnrichmentResult.

    Priority: caller overrides > LLM > rule-based fallback.

    - All three override fields set → pipeline skipped, result built from overrides.
    - Partial overrides → pipeline runs normally; override values win in the merge.
    - No overrides → rule-based first; LLM escalation if confidence < threshold.
    """
    ov = overrides
    if (
        ov is not None
        and ov.task_type is not None
        and ov.required_skills is not None
        and ov.difficulty is not None
    ):
        return EnrichmentResult(
            required_skills=ov.required_skills,
            difficulty=ov.difficulty,
            task_type=ov.task_type,
            domain_tags={},
            confidence=1.0,
        )

    result = enrich_rule_based(title, description)

    if result.confidence < _CONFIDENCE_THRESHOLD:
        try:
            raw = await llm_router.complete(
                _enrich_prompt.build_prompt(title, description or ""),
                CallType.ENRICH,
                json_mode=True,
            )
            parsed = _enrich_prompt.parse(raw)
            result = EnrichmentResult(
                required_skills=parsed.required_skills,
                difficulty=parsed.difficulty,
                task_type=parsed.task_type,
                domain_tags=parsed.domain_tags,
                confidence=1.0,
            )
        except Exception:
            pass  # keep rule-based result on LLM failure

    if ov is None:
        return result

    return EnrichmentResult(
        required_skills=ov.required_skills if ov.required_skills is not None else result.required_skills,
        difficulty=ov.difficulty      if ov.difficulty is not None             else result.difficulty,
        task_type=ov.task_type        if ov.task_type is not None              else result.task_type,
        domain_tags=result.domain_tags,
        confidence=result.confidence,
    )