from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import tool

from core.agents.tools.registry import tool_registry

if TYPE_CHECKING:
    from core.memory.agent_memory import AgentMemory


def _factory(*, memory: AgentMemory) -> object:
    @tool
    async def search_episodic_memory(agent_id: str, workspace_id: str, query: str) -> str:
        """Search the agent's past task experiences for patterns relevant to the current query.

        Use this when the current task resembles something the agent may have handled before.
        Pass the agent's own agent_id and workspace_id from the task context.
        """
        ctx = await memory.retrieve_for_task(agent_id, workspace_id, query)
        if not ctx.episodes:
            return "No relevant past experiences found."
        return "\n\n".join(f"[relevance {ep.score:.2f}] {ep.text}" for ep in ctx.episodes)

    return search_episodic_memory


tool_registry.register("search_episodic_memory", _factory)
