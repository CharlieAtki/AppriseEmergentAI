from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from core.agents.tools.definitions import AppriseToolDefinition, ToolCategory
from core.agents.tools.registry import tool_registry

if TYPE_CHECKING:
    from core.agents.tools.artifact_store import ArtifactStore

DEFINITION = AppriseToolDefinition(
    name="file_read",
    namespace="platform",
    description="Read a previously stored artifact by its storage reference.",
    input_schema={
        "type": "object",
        "properties": {
            "storage_ref": {
                "type": "string",
                "description": "The storage reference returned by file_write",
            }
        },
        "required": ["storage_ref"],
    },
    output_schema={"type": "string"},
    category=ToolCategory.MEMORY,
    config_class=None,
)


def _factory(*, artifact_store: ArtifactStore | None = None, **_: object) -> Callable:
    async def file_read(storage_ref: str) -> str:
        if artifact_store is None:
            return "Artifact store not configured."
        content = await artifact_store.read(storage_ref)
        return content.decode("utf-8", errors="replace")

    return file_read


tool_registry.register(DEFINITION, _factory)
