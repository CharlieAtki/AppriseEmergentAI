from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select

from core.database import get_session
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.stream_events import TaskCompletedStreamEvent
from core.memory.agent_memory import AgentMemory

logger = logging.getLogger(__name__)


@dataclass
class SocialMemoryHandler(EventHandler[TaskCompletedStreamEvent]):
    """Writes a social memory observation into every peer agent when a task completes.

    Peers learn about each other through observations stored in Qdrant's social
    memory collection. When agent A completes a task, every other active agent in
    the same workspace receives an observation recording what A did and how well.

    The peer query runs in one DB round-trip. Qdrant writes are fanned out via
    :func:`asyncio.gather` so all peers are updated concurrently. Failures on
    individual peer writes are caught and logged — a single Qdrant error must not
    prevent the remaining peers from receiving the observation.

    The handler never retries failed writes; transient Qdrant failures are
    acceptable here because social memory is soft state (the next task completion
    will produce another observation for the same agent).
    """

    memory: AgentMemory

    async def handle(self, event: TaskCompletedStreamEvent) -> None:
        workspace_id = str(event.workspace_id)
        completing_agent_id = str(event.completing_agent_id)

        async with get_session() as session:
            peers = (await session.execute(
                select(Agent).where(
                    Agent.workspace_id == event.workspace_id,
                    Agent.status == "active",
                    Agent.id != event.completing_agent_id,
                )
            )).scalars().all()

        await asyncio.gather(*(
            self._write_social(str(peer.id), completing_agent_id, workspace_id, event.quality_score, event.task_type)
            for peer in peers
        ))

    async def _write_social(
        self,
        peer_id: str,
        completing_agent_id: str,
        workspace_id: str,
        quality: float,
        task_type: str,
    ) -> None:
        try:
            await self.memory.store_social(
                peer_id,
                workspace_id,
                {
                    "text": (
                        f"Agent {completing_agent_id} completed a {task_type} task "
                        f"with quality score {quality:.2f}."
                    ),
                    "observed_agent_id": completing_agent_id,
                    "task_type": task_type,
                    "quality_score": quality,
                },
            )
        except Exception:
            logger.exception("social memory write failed for peer %s", peer_id)
