from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.intelligence.context import AgentContext, TaskEvaluationContext


class EvaluateResponse(BaseModel):
    decision: Literal["self_execute", "cfp", "decompose"]
    reasoning: str


def build_prompt(agent: AgentContext, task: TaskEvaluationContext) -> list[dict]:
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
        f"Agent: {agent.name}\n"
        f"Skills: {agent.skills}\n"
        f"Influence: {agent.influence:.2f}\n\n"
        f"Task title: {task.title}\n"
        f"Task description: {task.description}\n"
        f"Required skills: {task.required_skills}\n"
        f"Difficulty: {task.difficulty}\n"
        f"Domain tags: {task.domain_tags}\n"
        f"Delegation depth: {task.delegation_depth}\n"
        f"Depth exceeded: {task.depth_exceeded}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(raw: str) -> EvaluateResponse:
    from core.utils import strip_fences

    return EvaluateResponse.model_validate_json(strip_fences(raw))
