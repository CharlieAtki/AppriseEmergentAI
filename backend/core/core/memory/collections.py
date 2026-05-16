from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

COLLECTION_NAMES = ("mem_episodic", "mem_procedural", "mem_social")
VECTOR_SIZE = 384

_KEYWORD_INDEXES = ("workspace_id", "agent_id", "domain", "tier")


async def ensure_collections(client: AsyncQdrantClient) -> None:
    existing = {c.name for c in (await client.get_collections()).collections}
    for name in COLLECTION_NAMES:
        if name not in existing:
            await client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
        for field_name in _KEYWORD_INDEXES:
            try:
                await client.create_payload_index(
                    collection_name=name,
                    field_name=field_name,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass
