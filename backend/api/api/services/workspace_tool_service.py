from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from core.models.tools import Tool, WorkspaceTool
from core.repositories.tool_repository import ToolRepository


@dataclass(frozen=True)
class EnableToolCommand:
    """Immutable write intent — router constructs this from HTTP input; service never imports HTTP schemas."""

    workspace_id: uuid.UUID
    tool_id: uuid.UUID
    config: dict[str, Any] | None


@dataclass(frozen=True)
class WorkspaceToolData:
    """ORM boundary DTO — config values pass through; secret masking is a Phase 2 concern."""

    id: uuid.UUID
    namespace: str
    name: str
    display_name: str
    description: str
    category: str
    task_types: list[str]
    config_schema: dict[str, Any] | None
    enabled: bool
    config: dict[str, Any] | None

    @classmethod
    def from_rows(cls, tool: Tool, wt: WorkspaceTool | None) -> WorkspaceToolData:
        return cls(
            id=tool.id,
            namespace=tool.namespace,
            name=tool.name,
            display_name=tool.display_name,
            description=tool.description,
            category=tool.category,
            task_types=list(tool.task_types or []),
            config_schema=tool.config_schema,
            enabled=wt is not None,
            config=wt.config if wt is not None else None,
        )


class WorkspaceToolService:
    """Workspace tool configuration — accepts Commands, returns WorkspaceToolData; ORM never escapes."""

    def __init__(self, repo: ToolRepository) -> None:
        self._repo = repo

    async def list_tools(self, workspace_id: uuid.UUID) -> list[WorkspaceToolData]:
        rows = await self._repo.list_catalog_with_workspace_status(workspace_id)
        return [WorkspaceToolData.from_rows(tool, wt) for tool, wt in rows]

    async def enable_tool(self, cmd: EnableToolCommand) -> WorkspaceToolData | None:
        tool = await self._repo.get_tool(cmd.tool_id)
        if tool is None or not tool.is_active:
            return None
        wt = await self._repo.enable(cmd.workspace_id, cmd.tool_id, cmd.config)
        return WorkspaceToolData.from_rows(tool, wt)

    async def disable_tool(self, workspace_id: uuid.UUID, tool_id: uuid.UUID) -> bool:
        wt = await self._repo.get_workspace_tool(workspace_id, tool_id)
        if wt is None:
            return False
        await self._repo.disable(wt)
        return True
