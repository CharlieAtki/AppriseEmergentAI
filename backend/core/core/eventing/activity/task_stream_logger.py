"""Cross-process stream publishing facade for task coordination events.

This is the stream-transport equivalent of TaskActivityLogger. All payload
construction for task-related Redis Stream messages lives here — callers never
build raw dicts or call the bus directly.

Construct with ``TaskStreamLogger(wctx.bus.apublish)`` at the start of an ARQ job.

Consumers of each stream key:
    ``stream:task`` / ``task.created``   → TaskBiddingHandler (worker/handlers/bidding.py)
    ``stream:task`` / ``task.completed`` → SocialMemoryHandler (worker/handlers/social_memory.py)
    ``stream:cfp``  / ``cfp.issued``     → CfpHandler (worker/handlers/cfp.py)

Adding a field: change the StreamEvent class in core/eventing/events/stream_events.py.
The logger and subscriber stay in sync automatically because to_payload()/from_payload()
are colocated on the event class.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from core.eventing.activity.base import StreamPublishFn
from core.eventing.events.stream_events import (
    CfpIssuedStreamEvent,
    TaskCompletedStreamEvent,
    TaskCreatedStreamEvent,
)

if TYPE_CHECKING:
    from core.eventing.events.task_events import TaskSnapshot
    from core.models.agents import Agent
    from core.models.tasks import Task


class TaskStreamLogger:
    """Facade that constructs typed StreamEvents for task coordination.

    Mirrors TaskActivityLogger for in-process events — callers never construct
    raw dicts or touch the bus. Field shape is owned by the event classes in
    stream_events.py; this class only maps Task/Agent ORM attributes onto them.

    Never inject the bus itself — only the publish callable (``bus.apublish``).
    """

    def __init__(self, publish: StreamPublishFn) -> None:
        self._publish = publish

    async def task_created_from_snapshot(self, snapshot: TaskSnapshot) -> None:
        """Publish a ``task.created`` stream event from a snapshot.

        Used by the API bridge handler to forward an in-process TaskCreatedEvent
        to Redis Streams without the handler touching the bus directly.
        """
        await self._publish(
            TaskCreatedStreamEvent(
                task_id=snapshot.id,
                workspace_id=snapshot.workspace_id,
                organisation_id=snapshot.organisation_id,
                required_skills=snapshot.required_skills or {},
                difficulty=snapshot.difficulty,
                task_type=snapshot.task_type,
                domain_tags=snapshot.domain_tags,
            )
        )

    async def task_created(self, task: Task) -> None:
        """Publish a ``task.created`` event to trigger bidding for *task*.

        Called from two paths:
        - ``decompose_subtasks()`` — once per generated subtask after flush.
        - ``_release_to_pool()``      — when a CFP agent returns a task to "open".

        The task ORM object must be flushed (UUID assigned) before calling this.
        """
        await self._publish(
            TaskCreatedStreamEvent(
                task_id=task.id,
                workspace_id=task.workspace_id,
                organisation_id=task.organisation_id,
                required_skills=task.required_skills or {},
                difficulty=task.difficulty,
                task_type=task.task_type,
                domain_tags=task.domain_tags,
            )
        )

    async def task_completed(
        self,
        task: Task,
        agent_id: str,
        quality_score: float,
    ) -> None:
        """Publish a ``task.completed`` event after a successful self-execute.

        Only call this after Phase 6 (write results) has committed — the task must
        be in ``"completed"`` status in the DB before the stream event fires.
        """
        await self._publish(
            TaskCompletedStreamEvent(
                task_id=task.id,
                workspace_id=task.workspace_id,
                completing_agent_id=uuid.UUID(agent_id),
                quality_score=quality_score,
                task_type=task.task_type or "general",
            )
        )

    async def cfp_issued(self, task: Task, initiating_agent: Agent) -> None:
        """Publish a ``cfp.issued`` event to ``stream:cfp``.

        Consumed by CfpHandler (worker/handlers/cfp.py) which runs targeted
        bidding among agents other than the initiator. ``_release_to_pool()``
        follows this call with a ``task.created`` event on ``stream:task``
        as a fallback in case no agent wins the CFP round.
        """
        await self._publish(
            CfpIssuedStreamEvent(
                task_id=task.id,
                workspace_id=task.workspace_id,
                organisation_id=task.organisation_id,
                initiating_agent_id=initiating_agent.id,
                coordinator_agent_id=task.coordinator_agent_id,
                required_skills=task.required_skills or {},
                difficulty=task.difficulty,
                task_type=task.task_type,
                domain_tags=task.domain_tags,
            )
        )
