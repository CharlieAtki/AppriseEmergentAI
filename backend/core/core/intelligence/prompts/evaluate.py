from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.intelligence.context import AgentContext, TaskEvaluationContext


class EvaluateResponse(BaseModel):
    decision: Literal["self_execute", "cfp", "decompose"]
    reasoning: str


def build_prompt(
    agent: AgentContext, task: TaskEvaluationContext, decompose_difficulty_threshold: float
) -> list[dict]:
    system = (
        "You are deciding how an agent should handle an incoming task. "
        "Choose exactly one of three strategies:\n\n"
        "  self_execute — the agent handles the task directly using its tools.\n"
        "  cfp          — issue a Call for Proposals; another agent may be better suited.\n"
        "  decompose    — the task is too complex for one agent; break it into subtasks.\n\n"
        "Guidelines:\n"
        "- Prefer self_execute when the agent's skills cover the required skills.\n"
        "- Prefer cfp when required skills are missing or another agent is clearly better. "
        "cfp is skill-driven — influence_tier does not affect this choice.\n"
        f"- decompose is only valid when difficulty >= {decompose_difficulty_threshold}. "
        "Below that, do not decompose regardless of how many independent parts the task "
        "appears to have — choose self_execute or cfp instead.\n"
        '- If influence_tier is "high", lean further toward decompose for complex tasks — '
        "the agent has enough of a track record to act as a coordinator.\n"
        '- If influence_tier is "low", lean toward self_execute to build a track record, '
        "even when cfp/decompose would otherwise be plausible.\n"
        "- If depth_exceeded is true, you MUST choose self_execute regardless of other factors.\n\n"
        'Respond with JSON: {"decision": "...", "reasoning": "one sentence"}'
    )
    user = (
        f"Agent: {agent.name}\n"
        f"Skills: {agent.skills}\n"
        f"Influence tier: {agent.influence_tier} (raw={agent.influence:.2f})\n\n"
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
