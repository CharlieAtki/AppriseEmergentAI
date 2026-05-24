from __future__ import annotations

from dataclasses import dataclass

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