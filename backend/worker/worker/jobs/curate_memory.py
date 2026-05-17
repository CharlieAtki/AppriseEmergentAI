from __future__ import annotations

import logging

from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select

from core.database import get_session
from core.intelligence.call_types import CallType
from core.intelligence.prompts import curate as curate_prompt
from core.models.agents import Agent
from worker.context import get_worker_context

logger = logging.getLogger(__name__)


async def curate_memory(ctx: dict) -> None:
    """Cron job — runs nightly at midnight.

    For each active agent, loads all non-archived procedural rules from Qdrant,
    makes a single cheap LLM call (fast model — classification task, not reasoning)
    to identify redundant, contradictory, or stale entries, then archives flagged
    documents. Writes no DB rows — Qdrant metadata update is the only write.

    Without this, the procedural tier degrades over long runs as contradictory and
    redundant entries accumulate and contaminate retrieval.
    """
    wctx = get_worker_context()

    async with get_session() as session:
        agents = (await session.execute(
            select(Agent).where(Agent.status == "active")
        )).scalars().all()

    archived_total = 0
    for agent in agents:
        workspace_id = str(agent.workspace_id)
        agent_id     = str(agent.id)

        # Retrieve all non-archived procedural rules for this agent regardless of domain.
        # AgentMemory.retrieve_procedures_for_domain() filters by domain; we need all domains
        # here so we access the Qdrant client directly.
        all_rules, _ = await wctx.memory._client.scroll(
            collection_name="mem_procedural",
            scroll_filter=Filter(must=[
                FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id)),
                FieldCondition(key="agent_id",     match=MatchValue(value=agent_id)),
                FieldCondition(key="archived",      match=MatchValue(value=False)),
            ]),
            limit=100,
            with_payload=True,
        )

        if not all_rules:
            continue

        rule_dicts = [
            {
                "id":               str(p.id),
                "domain":           (p.payload or {}).get("domain", ""),
                "text":             (p.payload or {}).get("text", ""),
                "last_accessed_at": (p.payload or {}).get("last_accessed_at", "unknown"),
            }
            for p in all_rules
        ]

        raw = await wctx.llm_router.complete(
            curate_prompt.build_prompt(rule_dicts),
            CallType.CURATE_MEMORY,
            json_mode=True,
        )
        response = curate_prompt.parse(raw)

        if not response.flagged:
            continue

        flagged_ids = [f.id for f in response.flagged]
        for fid in flagged_ids:
            await wctx.memory._client.set_payload(
                collection_name="mem_procedural",
                payload={"archived": True},
                points=[fid],
            )
        archived_total += len(flagged_ids)
        logger.info(
            "curate_memory: archived %d rules for agent %s",
            len(flagged_ids), agent_id,
        )

    logger.info("curate_memory: complete — %d rules archived total", archived_total)
