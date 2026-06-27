from __future__ import annotations

from collections.abc import Callable

from core.agents.tooling.definitions import AppriseToolDefinition, ToolCategory
from core.agents.tooling.registry import tool_registry

DEFINITION = AppriseToolDefinition(
    name="execute_code",
    namespace="platform",
    display_name="Execute Code",
    description="Execute code in a sandboxed environment and return the output.",
    input_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "The code to execute"},
            "language": {
                "type": "string",
                "description": "Programming language (default: python)",
                "default": "python",
            },
        },
        "required": ["code"],
    },
    output_schema={"type": "string"},
    category=ToolCategory.ENGINEERING,
    task_types=frozenset({"code"}),
    config_class=None,
)


def _factory(**_: object) -> Callable:
    async def execute_code(code: str, language: str = "python") -> str:
        # Phase 2: sandboxed code execution
        return "Code execution not yet implemented."

    return execute_code


tool_registry.register(DEFINITION, _factory)
