from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class EvaluateResponse(BaseModel):
    decision: Literal["self_execute", "cfp", "decompose"]
    reasoning: str


def build_prompt(agent_ctx: dict[str, Any], task: dict[str, Any]) -> list[dict]:
    system = (
        "You are deciding how an agent should handle an incoming task. "
        "Choose exactly one of three strategies:\n\n"
        "  self_execute — the agent handles the task directly using its tools.\n"
        "  cfp          — issue a Call for Proposals; another agent may be better suited.\n"
        "  decompose    — the task is too complex for one agent; break it into subtasks.\n\n"
        "Guidelines:\n"
        "- Prefer self_execute when the agent's skills cover the required skills.\n"
        "- Prefer cfp when required skills are missing or another agent is clearly better.\n"
        "- Prefer decompose when difficulty >= 4 or the task has distinct independent parts.\n"
        "- If depth_exceeded is true, you MUST choose self_execute regardless of other factors.\n\n"
        'Respond with JSON: {"decision": "...", "reasoning": "one sentence"}'
    )
    user = (
        f"Agent: {agent_ctx.get('name')}\n"
        f"Skills: {agent_ctx.get('skills', {})}\n"
        f"Influence: {agent_ctx.get('influence', 0.0):.2f}\n\n"
        f"Task title: {task.get('title')}\n"
        f"Task description: {task.get('description')}\n"
        f"Required skills: {task.get('required_skills', {})}\n"
        f"Difficulty: {task.get('difficulty')}\n"
        f"Domain tags: {task.get('domain_tags', {})}\n"
        f"Delegation depth: {task.get('delegation_depth', 0)}\n"
        f"Depth exceeded: {task.get('depth_exceeded', False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(raw: str) -> EvaluateResponse:
    return EvaluateResponse.model_validate_json(raw)
