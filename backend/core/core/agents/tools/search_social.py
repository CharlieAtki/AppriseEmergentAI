from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import tool

from core.agents.tools._utils import _format_memory_items
from core.agents.tools.registry import tool_registry

if TYPE_CHECKING:
    from core.memory.agent_memory import AgentMemory


def _factory(*, memory: AgentMemory) -> object:
    @tool
    async def search_social_memory(agent_id: str, workspace_id: str, peer_agent_id: str) -> str:
        """Retrieve what this agent knows about a peer agent's capabilities and reliability.

        Use this when deciding whether to delegate to or collaborate with a specific peer.
        agent_id is the observing agent; peer_agent_id is the agent being looked up.
        Pass agent_id and workspace_id from the task context.
        """
        ctx = await memory.retrieve_for_task(
            agent_id,
            workspace_id,
            f"observations about agent {peer_agent_id}",
        )

        return _format_memory_items(ctx.social)

    return search_social_memory


tool_registry.register("search_social_memory", _factory)
