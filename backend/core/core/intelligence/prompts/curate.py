from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class FlaggedRule(BaseModel):
    id: str
    verdict: Literal["redundant", "contradicts", "stale"]
    reason: str


class CurateResponse(BaseModel):
    flagged: list[FlaggedRule]


def build_prompt(rules: list[dict[str, Any]]) -> list[dict]:
    rules_text = "\n".join(
        f"  [{r['id']}] (domain={r['domain']}, last_retrieved={r.get('last_accessed_at', 'unknown')}): {r['text']}"
        for r in rules
    )
    system = (
        "You are curating an agent's procedural memory to remove low-quality entries.\n\n"
        "Flag rules that are:\n"
        "  redundant   — same domain and essentially the same advice as another rule.\n"
        "  contradicts — directly contradicts another rule in the same domain.\n"
        "  stale       — last_retrieved is very old or the rule references outdated approaches.\n\n"
        "Only flag rules that clearly meet one of these criteria. When in doubt, do not flag.\n\n"
        'Respond with JSON: {"flagged": [{"id": "...", "verdict": "...", "reason": "..."}]}'
    )
    user = f"Procedural rules to review:\n{rules_text}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(raw: str) -> CurateResponse:
    return CurateResponse.model_validate_json(raw)
