from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskUpdatedEvent

if TYPE_CHECKING:
    from arq import ArqRedis

logger = logging.getLogger(__name__)


@dataclass
class WebhookDeliveryHandler(EventHandler[TaskUpdatedEvent]):
    arq_queue: ArqRedis

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status"):
            return
        if event.state.status != "completed":
            return
        if event.state.execution_id is None:
            return

        try:
            await self.arq_queue.enqueue_job(
                "deliver_webhook",
                execution_id=str(event.state.execution_id),
                workspace_id=str(event.state.workspace_id),
            )
        except Exception:
            logger.exception(
                "WebhookDeliveryHandler failed to enqueue for task=%s",
                event.state.id,
            )