"""In-memory tool registry and per-task tool builder.

**Separation of concerns**

``ToolRegistry`` owns two things only:
  1. The in-memory catalog — a ``(namespace, name) → ToolEntry`` map populated at import
     time via ``register()``.
  2. Assembling per-task ``BaseTool`` instances — ``build_for_task_type()`` queries the
     workspace's enabled tools via ``ToolRepository`` (data access), then applies closure
     injection and LangChain conversion here (tool construction).

Data access is deliberately delegated to ``ToolRepository``. The registry never holds a
session or runs SQLAlchemy directly — that would conflate the in-memory catalog layer
with the persistence layer and duplicate the JOIN logic already in the repository.

**Self-registration**

Importing a tool module IS registering it. Each tool file calls
``tool_registry.register(DEFINITION, _factory)`` at module level as a side effect.
``WorkerContext.build()`` imports them explicitly; the registry is populated before
``sync_tools()`` and ``build_for_task_type()`` are ever called.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from core.agents.tooling.definitions import CATEGORY_SKILL_TAGS, AppriseToolDefinition

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from core.agents.tooling.artifact_store import ArtifactStore
    from core.memory.agent_memory import AgentMemory
    from core.repositories.tool_repository import ToolRepository


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
        repo: ToolRepository,
        artifact_store: ArtifactStore | None = None,
    ) -> tuple[list[BaseTool], list[ToolEntry]]:
        """Build per-task LangChain BaseTool instances for the workspace's enabled tools.

        Data access is delegated to ``repo`` (ToolRepository owns the query). This method
        owns: task_type filtering, config parsing at the boundary (raw JSONB → typed
        config_class), closure injection, and LangChain tool construction.

        Only tools present in both the in-memory registry and the workspace_tools table
        are returned. Config JSONB → typed config_class conversion happens here — never
        passed as a raw dict downstream (Q16).

        # Phase 2 optimisation: cache per workspace_id with short TTL when throughput warrants it.
        """
        rows = await repo.list_enabled_for_workspace(workspace_id)

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
