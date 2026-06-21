from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from core.agents.tools.definitions import AppriseToolDefinition, ToolCategory
from core.agents.tools.registry import tool_registry

if TYPE_CHECKING:
    from core.agents.tools.artifact_store import ArtifactStore

DEFINITION = AppriseToolDefinition(
    name="file_write",
    namespace="platform",
    description=(
        "Write text content to the artifact store. "
        "Returns JSON with artifact_id and storage_ref for later retrieval via file_read."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path for the artifact (e.g. 'report.md')",
            },
            "content": {"type": "string", "description": "The text content to write"},
        },
        "required": ["path", "content"],
    },
    output_schema={"type": "object"},
    category=ToolCategory.MEMORY,
    config_class=None,
)


def _factory(
    *,
    workspace_id: UUID,
    organisation_id: UUID,
    artifact_store: ArtifactStore | None = None,
    **_: object,
) -> Callable:
    async def file_write(path: str, content: str) -> str:
        if artifact_store is None:
            return json.dumps({"error": "Artifact store not configured."})

        storage_ref = await artifact_store.write(workspace_id, path, content.encode("utf-8"))

        from core.database import get_session
        from core.models.artifacts import Artifact

        async with get_session() as session:
            artifact = Artifact(
                organisation_id=organisation_id,
                workspace_id=workspace_id,
                title=path,
                artifact_type="file",
                status="draft",
                storage_ref=storage_ref,
            )
            session.add(artifact)
            await session.commit()
            await session.refresh(artifact)
            return json.dumps({"artifact_id": str(artifact.id), "storage_ref": storage_ref})

    return file_write


tool_registry.register(DEFINITION, _factory)
