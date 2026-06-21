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
    name="search_procedural_memory",
    namespace="platform",
    display_name="Search Procedural Memory",
    description=(
        "Retrieve generalised rules the agent has developed for a skill domain. "
        "Use mid-execution when domain-specific knowledge would improve the outcome. "
        "domain should be a skill name (e.g. 'python', 'data_analysis', 'writing')."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Skill domain to search (e.g. 'python', 'writing')",
            },
            "query": {"type": "string", "description": "What to search for within the domain"},
        },
        "required": ["domain", "query"],
    },
    output_schema={"type": "string"},
    category=ToolCategory.MEMORY,
    config_class=None,
)


def _factory(*, memory: AgentMemory, agent_id: UUID, workspace_id: UUID, **_: object) -> Callable:
    async def search_procedural_memory(domain: str, query: str) -> str:
        if domain:
            items = await memory.retrieve_procedures_for_domain(
                str(agent_id), str(workspace_id), domain
            )
        else:
            ctx = await memory.retrieve_for_task(str(agent_id), str(workspace_id), query)
            items = ctx.procedures

        if not items:
            return "No procedural rules found for this domain."
        return _format_memory_items(items)

    return search_procedural_memory


tool_registry.register(DEFINITION, _factory)
