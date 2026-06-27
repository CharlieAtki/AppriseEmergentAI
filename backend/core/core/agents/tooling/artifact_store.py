from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Protocol
from uuid import UUID


class ArtifactStore(Protocol):
    async def write(self, workspace_id: UUID, path: str, content: bytes) -> str:
        """Write content and return a storage_ref (opaque pointer to the bytes)."""
        ...

    async def read(self, storage_ref: str) -> bytes:
        """Read content by storage_ref returned from a prior write."""
        ...


class LocalArtifactStore:
    """Phase 1 implementation — volume mount.

    Phase 2 replacement point: swap for an S3-compatible implementation.
    Interface (write/read) must remain stable.
    """

    def __init__(self, base_path: str | None = None) -> None:
        self._base = Path(
            base_path or os.environ.get("ARTIFACT_STORE_PATH", "/var/apprise/artifacts")
        )

    async def write(self, workspace_id: UUID, path: str, content: bytes) -> str:
        dest = self._base / str(workspace_id) / path.lstrip("/")
        await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(dest.write_bytes, content)
        return str(dest)

    async def read(self, storage_ref: str) -> bytes:
        return await asyncio.to_thread(Path(storage_ref).read_bytes)
