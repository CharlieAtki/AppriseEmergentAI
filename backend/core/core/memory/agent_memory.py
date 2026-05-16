from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from core.config import settings
from core.memory.embeddings import aembed
from core.memory.types import MemoryContext, MemoryItem, MemoryTier, SupersessionVerdict

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_item(tier: MemoryTier, point: Any) -> MemoryItem:
    payload = point.payload or {}
    return MemoryItem(
        tier=tier,
        id=str(point.id),
        score=getattr(point, "score", 1.0),
        text=payload.get("text", ""),
        payload=payload,
    )


def _base_filter(workspace_id: str, agent_id: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id)),
            FieldCondition(key="agent_id", match=MatchValue(value=agent_id)),
            FieldCondition(key="archived", match=MatchValue(value=False)),
        ]
    )


class AgentMemory:
    def __init__(self, client: AsyncQdrantClient, top_k: int = settings.memory.top_k) -> None:
        self._client = client
        self._top_k = top_k

    async def store_episode(
        self,
        agent_id: str,
        workspace_id: str,
        episode: dict[str, Any],
    ) -> str:
        point_id = str(uuid.uuid4())
        vector = await aembed(episode["text"])
        payload = {
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "tier": "episodic",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "archived": False,
            **episode,
        }
        await self._client.upsert(
            collection_name="mem_episodic",
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        return point_id

    async def store_procedure(
        self,
        agent_id: str,
        workspace_id: str,
        rule: str,
        domain: str,
        *,
        verdict: SupersessionVerdict | None = None,
        superseded_ids: list[str] | None = None,
        session: AsyncSession | None = None,
    ) -> str:
        from core.models.observability import ProceduralKnowledgeLog

        point_id = str(uuid.uuid4())
        vector = await aembed(rule)
        payload = {
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "tier": "procedural",
            "text": rule,
            "domain": domain,
            "verdict": verdict,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "archived": False,
        }
        await self._client.upsert(
            collection_name="mem_procedural",
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

        if superseded_ids:
            for sid in superseded_ids:
                await self._client.set_payload(
                    collection_name="mem_procedural",
                    payload={"archived": True, "superseded_by": point_id},
                    points=[sid],
                )

        if session is not None:
            log = ProceduralKnowledgeLog(
                workspace_id=uuid.UUID(workspace_id),
                agent_id=uuid.UUID(agent_id),
                domain=domain,
                rule_text=rule,
                vector_store_ref=point_id,
            )
            session.add(log)
            await session.flush()

        return point_id

    async def store_social(
        self,
        agent_id: str,
        workspace_id: str,
        observation: dict[str, Any],
    ) -> str:
        point_id = str(uuid.uuid4())
        vector = await aembed(observation["text"])
        payload = {
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "tier": "social",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "archived": False,
            **observation,
        }
        await self._client.upsert(
            collection_name="mem_social",
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        return point_id

    async def retrieve_for_task(
        self,
        agent_id: str,
        workspace_id: str,
        task_description: str,
        *,
        top_k: int | None = None,
    ) -> MemoryContext:
        k = top_k or self._top_k
        vector = await aembed(task_description)
        filt = _base_filter(workspace_id, agent_id)

        ep_hits, pr_hits, so_hits = await asyncio.gather(
            self._client.search("mem_episodic", query_vector=vector, query_filter=filt, limit=k, with_payload=True),
            self._client.search("mem_procedural", query_vector=vector, query_filter=filt, limit=k, with_payload=True),
            self._client.search("mem_social", query_vector=vector, query_filter=filt, limit=k, with_payload=True),
        )

        return MemoryContext(
            episodes=[_to_item("episodic", h) for h in ep_hits],
            procedures=[_to_item("procedural", h) for h in pr_hits],
            social=[_to_item("social", h) for h in so_hits],
        )

    async def retrieve_procedures_for_domain(
        self,
        agent_id: str,
        workspace_id: str,
        domain: str,
        *,
        top_k: int | None = None,
    ) -> list[MemoryItem]:
        k = top_k or self._top_k
        points, _ = await self._client.scroll(
            collection_name="mem_procedural",
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id)),
                    FieldCondition(key="agent_id", match=MatchValue(value=agent_id)),
                    FieldCondition(key="domain", match=MatchValue(value=domain)),
                    FieldCondition(key="archived", match=MatchValue(value=False)),
                ]
            ),
            limit=k,
            with_payload=True,
        )
        return [_to_item("procedural", p) for p in points]
