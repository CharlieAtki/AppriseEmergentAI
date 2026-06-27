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
    name="search_social_memory",
    namespace="platform",
    display_name="Search Social Memory",
    description=(
        "Retrieve what this agent knows about a peer agent's capabilities and reliability. "
        "Use when deciding whether to delegate to or collaborate with a specific peer."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "peer_agent_id": {"type": "string", "description": "UUID of the peer agent to look up"},
        },
        "required": ["peer_agent_id"],
    },
    output_schema={"type": "string"},
    category=ToolCategory.MEMORY,
    config_class=None,
)


def _factory(*, memory: AgentMemory, agent_id: UUID, workspace_id: UUID, **_: object) -> Callable:
    async def search_social_memory(peer_agent_id: str) -> str:
        ctx = await memory.retrieve_for_task(
            str(agent_id),
            str(workspace_id),
            f"observations about agent {peer_agent_id}",
        )
        if not ctx.social:
            return "No observations found for this agent."
        return _format_memory_items(ctx.social)

    return search_social_memory


tool_registry.register(DEFINITION, _factory)
