from __future__ import annotations

import logging

from sqlalchemy import select

from core.config import settings
from core.database import get_session
from core.models.agents import Agent
from worker.context import get_worker_context

logger = logging.getLogger(__name__)


async def decay(ctx: dict) -> None:
    """Cron job — runs every 30 seconds.

    Applies skill and influence decay across all active agents in all workspaces.
    Decay forces meaningful specialisation: without it every agent converges to
    high scores across all domains and the Gini coefficient collapses.

    Pure arithmetic — no LLM, no JobSpan, no observability events.
    """
    get_worker_context()  # guard: fail fast if worker context not initialised

    decay_rate = settings.SKILL_DECAY_RATE
    ema_alpha  = settings.INFLUENCE_EMA_ALPHA

    async with get_session() as session:
        agents = (await session.execute(
            select(Agent).where(Agent.status == "active")
        )).scalars().all()

        if not agents:
            return

        for agent in agents:
            if agent.skills:
                agent.skills = {
                    k: max(0.0, v * (1.0 - decay_rate))
                    for k, v in agent.skills.items()
                }
            if agent.influence is not None:
                agent.influence = agent.influence * (1.0 - ema_alpha)
            session.add(agent)
        # Single commit for all agents on context manager exit

    logger.debug("decay applied to %d agents", len(agents))
