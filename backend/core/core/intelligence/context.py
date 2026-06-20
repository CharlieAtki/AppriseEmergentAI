from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentContext:
    name: str
    skills: dict[str, float]
    influence: float


@dataclass(frozen=True)
class TaskEvaluationContext:
    title: str
    description: str | None
    required_skills: dict[str, float]
    difficulty: float | None
    domain_tags: dict[str, float]
    task_type: str | None
    delegation_depth: int
    depth_exceeded: bool
