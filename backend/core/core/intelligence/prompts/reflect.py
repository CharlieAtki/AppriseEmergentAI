from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ReflectResponse(BaseModel):
    skill_deltas: dict[str, float]
    generalised_rule: str | None
    verdict: Literal["supersedes", "complements", "contradicts"] | None
    superseded_ids: list[str] | None = None


def build_prompt(
    task: dict[str, Any],
    result: dict[str, Any],
    quality_score: float,
    existing_rules: list[dict[str, Any]] | None = None,
) -> list[dict]:
    existing_block = ""
    if existing_rules:
        rules_text = "\n".join(
            f"  [{r['id']}] ({r['domain']}): {r['text']}" for r in existing_rules
        )
        existing_block = (
            f"\nExisting procedural rules for this domain:\n{rules_text}\n"
            "If your new rule supersedes, complements, or contradicts any of these, "
            "set 'verdict' and 'superseded_ids' accordingly. Otherwise leave them null.\n"
        )

    system = (
        "You are reflecting on a completed task to update an agent's skills and knowledge.\n\n"
        "Your output has two parts:\n"
        "1. skill_deltas: a dict of skill_name → float delta in [-0.2, +0.3]. "
        "Positive for skills exercised successfully, negative for skills that failed.\n"
        "2. generalised_rule: a single reusable rule the agent learned (null if task was trivial).\n"
        f"{existing_block}"
        'Respond with JSON matching: '
        '{"skill_deltas": {}, "generalised_rule": null or "string", '
        '"verdict": null or "supersedes"|"complements"|"contradicts", '
        '"superseded_ids": null or ["id1"]}'
    )
    user = (
        f"Task: {task.get('title')}\n"
        f"Description: {task.get('description')}\n"
        f"Task type: {task.get('task_type')}\n"
        f"Required skills: {task.get('required_skills', {})}\n"
        f"Difficulty: {task.get('difficulty')}\n\n"
        f"Result summary: {result.get('summary', result.get('text', ''))}\n"
        f"Tools used: {result.get('tool_trace', [])}\n"
        f"Quality score: {quality_score:.2f}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(raw: str) -> ReflectResponse:
    return ReflectResponse.model_validate_json(raw)
