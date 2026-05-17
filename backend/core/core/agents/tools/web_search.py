from __future__ import annotations

from langchain_core.tools import tool

from core.agents.tools.registry import tool_registry


def _factory(**_kwargs: object) -> object:
    @tool
    async def web_search(query: str) -> str:
        """Search the web for information relevant to the current task."""
        return "Web search not yet implemented."

    return web_search


tool_registry.register("web_search", _factory)
