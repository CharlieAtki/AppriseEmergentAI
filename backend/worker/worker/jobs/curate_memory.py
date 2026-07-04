from __future__ import annotations

import logging
from typing import Any

from core.database import get_session
from core.intelligence import structured_call
from core.intelligence.call_types import CallType
from core.intelligence.prompts import curate as curate_prompt
from core.intelligence.prompts.curate import CurateResponse
from core.memory.types import ProceduralRule
from core.models.agents import Agent
from sqlalchemy import select

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

    # Cross-workspace query — intentionally not on AgentRepository, which is workspace-scoped.
    # This platform-admin query will likely graduate to a dedicated admin query interface.
    async with get_session() as session:
        agents = (
            (await session.execute(select(Agent).where(Agent.status == "active"))).scalars().all()
        )

    archived_total = 0
    for agent in agents:
        workspace_id = str(agent.workspace_id)
        agent_id = str(agent.id)

        all_rules = await wctx.memory.scroll_all_procedures(agent_id, workspace_id)

        if not all_rules:
            continue

        rules = [ProceduralRule.from_item(item) for item in all_rules]

        try:
            response = await structured_call.run(
                wctx.llm_router,
                CallType.CURATE_MEMORY,
                curate_prompt.build_prompt(rules),
                curate_prompt.parse,
                fallback=CurateResponse(flagged=[]),
            )
        except Exception:
            logger.exception("curate_memory: LLM call failed for agent %s, skipping", agent_id)
            continue

        if not response.flagged:
            continue

        flagged_ids = [f.id for f in response.flagged]
        await wctx.memory.archive_procedures(flagged_ids)
        archived_total += len(flagged_ids)
        logger.info(
            "curate_memory: archived %d rules for agent %s",
            len(flagged_ids),
            agent_id,
        )

    logger.info("curate_memory: complete — %d rules archived total", archived_total)
