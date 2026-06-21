from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.agents.tools.definitions import CATEGORY_SKILL_TAGS, AppriseToolDefinition
from core.models.tools import Tool, WorkspaceTool

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from core.agents.tools.artifact_store import ArtifactStore
    from core.memory.agent_memory import AgentMemory


@dataclass(frozen=True)
class ToolEntry:
    defn: AppriseToolDefinition
    factory: Callable[..., Callable[..., Any]]


class ToolRegistry:
    """Self-registration registry for agent tools.

    Mirrors ModelRegistry: module-level singleton, dependency-free, populated
    by tool modules calling register() at import time as a side effect.
    Keyed by (namespace, name) to prevent cross-namespace collisions.
    """

    def __init__(self) -> None:
        self._tools: dict[tuple[str, str], ToolEntry] = {}

    def register(
        self, defn: AppriseToolDefinition, factory: Callable[..., Callable[..., Any]]
    ) -> None:
        self._tools[(defn.namespace, defn.name)] = ToolEntry(defn=defn, factory=factory)

    async def build_for_task_type(
        self,
        task_type: str,
        workspace_id: UUID,
        memory: AgentMemory,
        agent_id: UUID,
        organisation_id: UUID,
        session: AsyncSession,
        artifact_store: ArtifactStore | None = None,
    ) -> tuple[list[BaseTool], list[ToolEntry]]:
        """Query enabled workspace tools and build LangChain BaseTool instances.

        Only tools registered in both the in-memory registry and the workspace_tools
        table are returned. Config JSONB is parsed into the typed config_class at this
        boundary — never passed as raw dict downstream.

        # Phase 2 optimisation: cache per workspace_id with short TTL when throughput warrants it.
        """
        result = await session.execute(
            select(WorkspaceTool, Tool)
            .join(Tool, WorkspaceTool.tool_id == Tool.id)
            .where(WorkspaceTool.workspace_id == workspace_id)
            .where(Tool.is_active.is_(True))
        )
        rows = result.all()

        built_tools: list[BaseTool] = []
        active_entries: list[ToolEntry] = []

        for wt, tool in rows:
            entry = self._tools.get((tool.namespace, tool.name))
            if entry is None:
                continue  # DB row exists but definition not registered — stale row

            if entry.defn.task_types and task_type not in entry.defn.task_types:
                continue

            # Parse config at the boundary — registry owns the raw dict → typed object conversion.
            typed_config: Any = None
            if entry.defn.config_class is not None and wt.config:
                try:
                    typed_config = entry.defn.config_class(**wt.config)
                except TypeError:
                    continue  # config shape mismatch — skip tool rather than propagate bad state

            fn = entry.factory(
                memory=memory,
                agent_id=agent_id,
                workspace_id=workspace_id,
                organisation_id=organisation_id,
                config=typed_config,
                artifact_store=artifact_store,
            )
            built_tools.append(self._build_langchain_tool(entry.defn, fn))
            active_entries.append(entry)

        return built_tools, active_entries

    def get_skill_tag_map(self, entries: list[ToolEntry]) -> dict[str, frozenset[str]]:
        """Return {tool_name: skill_tags} for the active tool set. Feeds RL update in reflect job."""
        return {e.defn.name: CATEGORY_SKILL_TAGS.get(e.defn.category, frozenset()) for e in entries}

    def _build_langchain_tool(
        self, defn: AppriseToolDefinition, fn: Callable[..., Any]
    ) -> BaseTool:
        # Phase 2: if defn.tool_type == "mcp" → build MCP client wrapper instead of StructuredTool.
        from langchain_core.tools import StructuredTool

        return StructuredTool.from_function(
            coroutine=fn,
            name=defn.name,
            description=defn.description,
        )

    def available_tools(self) -> list[ToolEntry]:
        return list(self._tools.values())


tool_registry = ToolRegistry()
