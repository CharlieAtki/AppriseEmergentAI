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
    """Enqueues a deliver_webhook ARQ job when a task reaches "completed".

    Only fires on "completed" — failed tasks do not trigger webhook delivery.
    Guards on execution_id presence because the event is emitted before the
    execution row is guaranteed to exist on decompose/CFP paths.

    Retry logic lives entirely inside deliver_webhook — this handler does not
    re-raise on enqueue failure because a lost enqueue is preferable to blocking
    all other TaskUpdatedEvent handlers on a Redis error.
    """

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