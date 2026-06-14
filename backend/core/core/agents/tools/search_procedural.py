from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import tool

from core.agents.tools.registry import tool_registry

if TYPE_CHECKING:
    from core.memory.agent_memory import AgentMemory


def _factory(*, memory: AgentMemory) -> object:
    @tool
    async def search_procedural_memory(
        agent_id: str, workspace_id: str, domain: str, query: str
    ) -> str:
        """Retrieve generalised rules the agent has developed for a skill domain.

        Use this mid-execution when domain-specific knowledge would improve the outcome.
        domain should be a skill name (e.g. 'python', 'data_analysis', 'writing').
        Pass the agent's own agent_id and workspace_id from the task context.
        """
        if domain:
            items = await memory.retrieve_procedures_for_domain(agent_id, workspace_id, domain)
        else:
            ctx = await memory.retrieve_for_task(agent_id, workspace_id, query)
            items = ctx.procedures

        if not items:
            return "No procedural rules found for this domain."
        return "\n\n".join(f"[relevance {item.score:.2f}] {item.text}" for item in items)

    return search_procedural_memory


tool_registry.register("search_procedural_memory", _factory)
