from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentContext:
    name: str
    skills: Mapping[str, float]
    influence: float


@dataclass(frozen=True)
class TaskEvaluationContext:
    title: str
    description: str | None
    required_skills: Mapping[str, float]
    difficulty: float | None
    domain_tags: Mapping[str, float]
    task_type: str | None
    delegation_depth: int
    depth_exceeded: bool
