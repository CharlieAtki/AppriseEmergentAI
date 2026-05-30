from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class TaskContext:
    title: str
    description: str | None
    task_type: str | None
    required_skills: dict[str, float]
    difficulty: float | None


@dataclass(frozen=True)
class ResultContext:
    summary: str
    tool_trace: list


@dataclass(frozen=True)
class ExistingRule:
    id: str
    domain: str
    text: str


class ReflectResponse(BaseModel):
    skill_deltas: dict[str, float]
    generalised_rule: str | None
    verdict: Literal["supersedes", "complements", "contradicts"] | None
    superseded_ids: list[str] | None = None


def build_prompt(
    task: TaskContext,
    result: ResultContext,
    quality_score: float,
    existing_rules: list[ExistingRule] | None = None,
) -> list[dict]:
    existing_block = ""
    if existing_rules:
        rules_text = "\n".join(
            f"  [{r.id}] ({r.domain}): {r.text}" for r in existing_rules
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
        f"Task: {task.title}\n"
        f"Description: {task.description}\n"
        f"Task type: {task.task_type}\n"
        f"Required skills: {task.required_skills}\n"
        f"Difficulty: {task.difficulty}\n\n"
        f"Result summary: {result.summary}\n"
        f"Tools used: {result.tool_trace}\n"
        f"Quality score: {quality_score:.2f}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(raw: str) -> ReflectResponse:
    return ReflectResponse.model_validate_json(raw)
