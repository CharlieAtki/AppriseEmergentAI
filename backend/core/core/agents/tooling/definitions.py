from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, get_args, get_type_hints


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
    display_name: str  # human-readable label shown in the workspace tools UI
    description: str  # what the LLM reads to decide when to call this tool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    category: ToolCategory
    task_types: frozenset[str] = field(default_factory=frozenset)  # empty = all task types
    config_class: type | None = (
        None  # frozen dataclass for typed workspace config; None = no config
    )

    def config_json_schema(self) -> dict[str, Any] | None:
        """Derive a JSON Schema dict from config_class for workspace UI form rendering.

        Called by sync_tools() to populate tools.config_schema in the DB. The definition
        owns this derivation — it declared the config_class, so it knows how to describe it.
        Returns None when no config_class is set or when no recognised fields are found.
        """
        if self.config_class is None or not dataclasses.is_dataclass(self.config_class):
            return None
        try:
            hints = get_type_hints(self.config_class)
        except Exception:
            return None

        _PRIMITIVE: dict[type, str] = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
        }

        def _field_schema(hint: Any) -> dict[str, Any]:
            if hint in _PRIMITIVE:
                return {"type": _PRIMITIVE[hint]}
            # X | None — get_args() covers typing.Optional, typing.Union, and
            # Python 3.10+ union syntax (types.UnionType) uniformly.
            args = get_args(hint)
            if args and type(None) in args:
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1 and non_none[0] in _PRIMITIVE:
                    return {"type": [_PRIMITIVE[non_none[0]], "null"]}
            return {}

        properties = {
            f.name: _field_schema(hints[f.name])
            for f in dataclasses.fields(self.config_class)
            if f.name in hints
        }
        return {"type": "object", "properties": properties} if properties else None
