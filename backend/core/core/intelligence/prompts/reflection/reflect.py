from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from core.utils import strip_fences

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskContext:
    """Task metadata passed to prompt builders. Extracted from ReflectContext."""

    title: str
    description: str | None
    task_type: str | None
    required_skills: dict[str, float]
    difficulty: float | None


@dataclass(frozen=True)
class ResultContext:
    """Execution output passed to prompt builders. Extracted from ReflectContext."""

    summary: str  # artifact text on success; error message on failure
    tool_trace: tuple[dict[str, Any], ...]  # sequence of tool call dicts from the graph execution


@dataclass(frozen=True)
class ExistingRule:
    """A procedural rule already stored in Qdrant, injected for supersession decisions.

    Only passed to ``build_prompt`` on the full_reflect path. ``id`` is the Qdrant
    point ID — returned in ``superseded_ids`` when this rule is replaced.
    """

    id: str
    domain: str
    text: str


class ReflectOutput(BaseModel):
    """Parsed output from the unified REFLECT LLM call.

    ``skill_domains`` and ``new_skill_suggestions`` are always present (may be empty).
    ``generalised_rule``, ``verdict``, and ``superseded_ids`` are only populated on
    the full_reflect path — the lightweight prompt does not ask for them and they
    default to None / empty list.
    """

    skill_domains: list[str]
    new_skill_suggestions: list[str] = []
    generalised_rule: str | None = None
    verdict: Literal["supersedes", "complements", "contradicts"] | None = None
    superseded_ids: list[str] = []


def build_prompt(
    task: TaskContext,
    result: ResultContext,
    quality_score: float,
    status: str,
    full_reflect: bool,
    existing_rules: list[ExistingRule] | None = None,
) -> list[dict]:
    """Build the system+user message pair for the unified REFLECT call.

    Two paths controlled by ``full_reflect``:

    Lightweight (``full_reflect=False``): classify which skills from the agent's
    required skill set were exercised and suggest new skills not already present.
    Used for routine executions (difficulty < 3.0 and step_count <= 3).

    Full (``full_reflect=True``): additionally extract a generalised rule and declare
    a verdict against ``existing_rules`` if provided.
      - Completed tasks: HOW-TO rule — a reusable approach or pattern.
      - Failed tasks: WHAT-TO-AVOID rule — an anti-pattern or failure mode.

    Rule quality constraint injected in the full path:
      The ``generalised_rule`` must reference a specific tool, error type, code
      pattern, or domain artifact that appeared in the tool_trace or result.
      Generic advice ("be thorough", "handle errors carefully") must return null.
      One rule maximum.

    Both paths use the same JSON response schema so ``parse()`` handles both
    without branching.
    """
    skills_str = ", ".join(f"{k}:{v:.2f}" for k, v in task.required_skills.items()) or "none"
    tool_trace_list = list(result.tool_trace)
    if len(tool_trace_list) > 12:
        logger.warning(
            "reflect prompt: tool_trace truncated from %d to 12 entries", len(tool_trace_list)
        )
    tool_summary = (
        ", ".join(t.get("tool", "?") for t in tool_trace_list[:12]) if tool_trace_list else "none"
    )

    user = (
        f"Task: {task.title}\n"
        f"Description: {task.description or 'none'}\n"
        f"Task type: {task.task_type or 'general'}\n"
        f"Required skills: {skills_str}\n"
        f"Difficulty: {task.difficulty or 'unknown'}\n\n"
        f"Status: {status}\n"
        f"Result: {result.summary or '(no output)'}\n"
        f"Tools used: {tool_summary}\n"
        f"Quality score: {quality_score:.2f}"
    )

    if not full_reflect:
        system = (
            "You are updating an AI agent's skill profile after a task execution.\n\n"
            "Return:\n"
            "  skill_domains: list of skill names from the required skills that were "
            "meaningfully exercised. Omit skills not relevant to this task.\n"
            "  new_skill_suggestions: skill names NOT in the required set that this "
            "task revealed the agent used. Empty list if none.\n\n"
            'Respond with JSON: {"skill_domains": [...], "new_skill_suggestions": [...]}'
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    # Full reflect path — rule extraction + supersession
    existing_block = ""
    if existing_rules:
        rules_text = "\n".join(f"  [{r.id}] ({r.domain}): {r.text}" for r in existing_rules)
        existing_block = (
            f"\nExisting procedural rules for this domain:\n{rules_text}\n\n"
            "If your new rule supersedes, complements, or contradicts any of these, "
            "set 'verdict' and 'superseded_ids' accordingly. Otherwise leave them null.\n"
        )

    if status == "completed":
        rule_instruction = (
            "Extract a generalised HOW-TO rule — a reusable approach or pattern "
            "that would improve future performance on similar tasks.\n"
        )
    else:
        rule_instruction = (
            "Extract a WHAT-TO-AVOID rule — a specific anti-pattern or failure mode "
            "that should not be repeated.\n"
        )

    system = (
        "You are updating an AI agent's skill profile and extracting a procedural rule "
        "from a task execution.\n\n"
        "Return:\n"
        "  skill_domains: list of skill names from the required skills that were "
        "meaningfully exercised.\n"
        "  new_skill_suggestions: skill names not in the required set that this task "
        "revealed. Empty list if none.\n"
        f"  generalised_rule: {rule_instruction}"
        "The rule MUST reference a specific tool name, error type, code pattern, or "
        "domain artifact that appeared in the tool trace or result. Return null for "
        "generic advice ('be thorough', 'verify assumptions', 'handle errors carefully'). "
        "Only extract a rule if the execution was non-trivial. One rule maximum.\n"
        f"{existing_block}"
        'Respond with JSON: {"skill_domains": [...], "new_skill_suggestions": [...], '
        '"generalised_rule": null or "string", "verdict": null or '
        '"supersedes"|"complements"|"contradicts", "superseded_ids": []}'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(raw: str) -> ReflectOutput:
    """Parse the raw JSON string returned by the LLM into a ReflectOutput."""
    return ReflectOutput.model_validate_json(strip_fences(raw))
