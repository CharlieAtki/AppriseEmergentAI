from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class ToolEntry:
    name: str
    # Empty frozenset means available for all task types.
    task_types: frozenset[str]
    factory: Callable[..., BaseTool]


class ToolRegistry:
    """Observable self-registration registry for agent tools.

    Mirrors ModelRegistry: module-level singleton, dependency-free, populated
    by tool modules calling register() at import time as a side effect.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def register(
        self,
        name: str,
        factory: Callable[..., BaseTool],
        *,
        task_types: frozenset[str] | set[str] = frozenset(),
    ) -> None:
        self._tools[name] = ToolEntry(
            name=name,
            task_types=frozenset(task_types),
            factory=factory,
        )

    def build_for_task_type(self, task_type: str, **kwargs: Any) -> list[BaseTool]:
        """Instantiate all tools applicable to task_type, injecting kwargs into each factory."""
        return [
            entry.factory(**kwargs)
            for entry in self._tools.values()
            if not entry.task_types or task_type in entry.task_types
        ]

    def available_tools(self) -> list[ToolEntry]:
        return list(self._tools.values())


tool_registry = ToolRegistry()
