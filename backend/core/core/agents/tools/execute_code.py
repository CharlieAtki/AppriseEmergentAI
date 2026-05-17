from __future__ import annotations

from langchain_core.tools import tool

from core.agents.tools.registry import tool_registry


def _factory(**_kwargs: object) -> object:
    @tool
    async def execute_code(code: str, language: str = "python") -> str:
        """Execute code in a sandboxed environment and return the output."""
        return "Code execution not yet implemented."

    return execute_code


tool_registry.register("execute_code", _factory, task_types=frozenset({"code"}))
