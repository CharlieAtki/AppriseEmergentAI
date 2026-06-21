from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from core.agents.tooling._utils import _format_memory_items
from core.agents.tooling.definitions import AppriseToolDefinition, ToolCategory
from core.agents.tooling.registry import tool_registry

if TYPE_CHECKING:
    from core.memory.agent_memory import AgentMemory

DEFINITION = AppriseToolDefinition(
    name="search_episodic_memory",
    namespace="platform",
    display_name="Search Episodic Memory",
    description=(
        "Search the agent's past task experiences for patterns relevant to the current query. "
        "Use when the current task resembles something the agent may have handled before."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for in past experiences"}
        },
        "required": ["query"],
    },
    output_schema={"type": "string"},
    category=ToolCategory.MEMORY,
    config_class=None,
)


def _factory(*, memory: AgentMemory, agent_id: UUID, workspace_id: UUID, **_: object) -> Callable:
    async def search_episodic_memory(query: str) -> str:
        ctx = await memory.retrieve_for_task(str(agent_id), str(workspace_id), query)
        if not ctx.episodes:
            return "No relevant past experiences found."
        return _format_memory_items(ctx.episodes)

    return search_episodic_memory


tool_registry.register(DEFINITION, _factory)
