from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SubtaskSpec(BaseModel):
    title: str
    description: str
    required_skills: dict[str, float]
    difficulty: float


class DecomposeResponse(BaseModel):
    subtasks: list[SubtaskSpec]


def build_prompt(agent_ctx: dict[str, Any], task: dict[str, Any]) -> list[dict]:
    system = (
        "You are breaking a complex task into subtasks that independent agents can execute.\n\n"
        "Rules:\n"
        "- Each subtask must be independently executable (no implicit dependency on another subtask's output "
        "unless that dependency is made explicit in the description).\n"
        "- Subtasks should be narrower in scope than the parent — if a subtask still feels complex, break it further.\n"
        "- required_skills values are importance weights in [0.0, 1.0].\n"
        "- difficulty is in [1.0, 5.0].\n"
        "- Aim for 2–6 subtasks. More than 6 is a sign the decomposition is too granular.\n\n"
        'Respond with JSON: {"subtasks": [{"title": "...", "description": "...", '
        '"required_skills": {}, "difficulty": 2.0}, ...]}'
    )
    user = (
        f"Agent: {agent_ctx.get('name')}\n\n"
        f"Task title: {task.get('title')}\n"
        f"Task description: {task.get('description')}\n"
        f"Required skills: {task.get('required_skills', {})}\n"
        f"Difficulty: {task.get('difficulty')}\n"
        f"Domain tags: {task.get('domain_tags', {})}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(raw: str) -> DecomposeResponse:
    return DecomposeResponse.model_validate_json(raw)
