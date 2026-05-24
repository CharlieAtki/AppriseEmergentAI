from __future__ import annotations

import logging
from dataclasses import dataclass

from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskUpdatedEvent
from core.memory.agent_memory import AgentMemory

logger = logging.getLogger(__name__)


@dataclass
class EpisodicMemoryHandler(EventHandler[TaskUpdatedEvent]):
    """Writes an episodic memory entry for the executing agent when a self-execute task completes.

    Episodic memory records what this specific agent did — the task it worked on,
    its type, and the quality of the outcome. Distinct from social memory, which
    records observations about peer agents across the workspace.

    Only fires for the self-execute path. Decompose and CFP executions have no
    quality_score on the snapshot — the task was delegated, not worked on.

    Phase 2 extension point: when ArtifactContribution records exist, this handler
    can be updated to include content_ref and operation_type in the episode payload.
    execute_task does not need to change — the handler queries the artifact tables
    independently.
    """

    memory: AgentMemory

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status") or event.state.status != "completed":
            return
        if event.state.execution_path != "self_execute":
            return
        if event.state.executing_agent_id is None or event.state.quality_score is None:
            return

        task_type_str = event.state.task_type or "general"
        domains = ", ".join(event.state.domain_tags.keys()) if event.state.domain_tags else "none"
        text = (
            f"Completed {task_type_str} task: {event.state.title}. "
            f"Domains: {domains}. "
            f"Quality: {event.state.quality_score:.2f}."
        )

        await self.memory.store_episode(
            str(event.state.executing_agent_id),
            str(event.state.workspace_id),
            {
                "text":          text,
                "task_id":       str(event.state.id),
                "task_type":     event.state.task_type,
                "domain_tags":   event.state.domain_tags or {},
                "difficulty":    event.state.difficulty,
                "quality_score": event.state.quality_score,
            },
        )
        logger.debug(
            "EpisodicMemoryHandler: wrote episode for agent=%s task=%s quality=%.3f",
            event.state.executing_agent_id, event.state.id, event.state.quality_score,
        )
