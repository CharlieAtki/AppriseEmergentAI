from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolCategory(StrEnum):
    RESEARCH = "research"
    ENGINEERING = "engineering"
    WRITING = "writing"
    COORDINATION = "coordination"
    MEMORY = "memory"


CATEGORY_SKILL_TAGS: dict[ToolCategory, frozenset[str]] = {
    ToolCategory.RESEARCH: frozenset({"research", "retrieval"}),
    ToolCategory.ENGINEERING: frozenset({"coding", "debugging", "testing"}),
    ToolCategory.WRITING: frozenset({"writing", "review"}),
    ToolCategory.COORDINATION: frozenset({"coordination"}),
    ToolCategory.MEMORY: frozenset(),  # infrastructure — no RL update
}


@dataclass(frozen=True)
class AppriseToolDefinition:
    name: str
    namespace: str  # "platform" | "mcp.{server_name}" | "custom"
    description: str  # what the LLM reads to decide when to call this tool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    category: ToolCategory
    task_types: frozenset[str] = field(default_factory=frozenset)  # empty = all task types
    config_class: type | None = (
        None  # frozen dataclass for typed workspace config; None = no config
    )
