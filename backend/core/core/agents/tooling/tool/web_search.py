from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from core.agents.tooling.definitions import AppriseToolDefinition, ToolCategory
from core.agents.tooling.registry import tool_registry


@dataclass(frozen=True)
class WebSearchConfig:
    api_key: str | None = None


DEFINITION = AppriseToolDefinition(
    name="web_search",
    namespace="platform",
    display_name="Web Search",
    description="Search the web for information relevant to the current task.",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "The search query"}},
        "required": ["query"],
    },
    output_schema={"type": "string"},
    category=ToolCategory.RESEARCH,
    config_class=WebSearchConfig,
)


def _factory(*, config: WebSearchConfig | None = None, **_: object) -> Callable:
    async def web_search(query: str) -> str:
        # Phase 2: use config.api_key with search provider SDK
        return "Web search not yet implemented."

    return web_search


tool_registry.register(DEFINITION, _factory)
