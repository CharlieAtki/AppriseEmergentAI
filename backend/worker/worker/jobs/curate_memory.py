from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from core.database import get_session
from core.intelligence.call_types import CallType
from core.intelligence.prompts import curate as curate_prompt
from core.models.agents import Agent
from worker.context import get_worker_context

logger = logging.getLogger(__name__)


async def curate_memory(ctx: dict[str, Any]) -> None:
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

        all_rules = await wctx.memory.scroll_all_procedures(agent_id, workspace_id)

        if not all_rules:
            continue

        rule_dicts = [
            {
                "id":               item.id,
                "domain":           (item.payload or {}).get("domain", ""),
                "text":             item.text,
                "last_accessed_at": (item.payload or {}).get("last_accessed_at", "unknown"),
            }
            for item in all_rules
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
        await wctx.memory.archive_procedures(flagged_ids)
        archived_total += len(flagged_ids)
        logger.info(
            "curate_memory: archived %d rules for agent %s",
            len(flagged_ids), agent_id,
        )

    logger.info("curate_memory: complete — %d rules archived total", archived_total)
