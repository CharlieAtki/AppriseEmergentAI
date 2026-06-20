from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.config import settings
from core.coordination.influence import compute_influence_ema
from core.coordination.task_state import TaskStateMachine
from core.database import get_session
from core.eventing.bus.handlers import EventHandler
from core.eventing.events.task_events import TaskUpdatedEvent
from core.models.observability import InfluenceSnapshot
from core.models.tasks import TaskExecution
from core.repositories.agent_repository import AgentRepository
from core.repositories.task_repository import TaskRepository
from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def compute_delegation_credits(
    task_id: uuid.UUID,
    workspace_id: uuid.UUID,
    quality: float,
    session: AsyncSession,
) -> list[tuple[uuid.UUID, float]]:
    """Return (agent_id, quality_signal) for every agent in a task's delegation chain.

    Queries TaskExecution rows for the given task where execution_path is "cfp" or
    "decompose". Each row represents an agent that took a coordination action on the task
    (routing or structuring) rather than executing it directly.

    Credit signals:
      "decompose": full quality signal — the agent structured the problem; every subtask
                   outcome is a direct consequence of that structure.
      "cfp":       quality * CFP_COORDINATOR_CREDIT (0.5) — the agent routed the task
                   but did not structure or execute it; partial credit for routing judgment.

    Multiple agents may appear (e.g. CFP initiator + decomposer in a CFP→Decompose chain).
    All are returned in a single query — one DB round-trip regardless of chain length.
    """
    rows = (
        await session.execute(
            select(TaskExecution.agent_id, TaskExecution.execution_path).where(
                TaskExecution.task_id == task_id,
                TaskExecution.workspace_id == workspace_id,
                TaskExecution.execution_path.in_(["cfp", "decompose"]),
                TaskExecution.status == "completed",
            )
        )
    ).all()

    result: list[tuple[uuid.UUID, float]] = []
    for agent_id, path in rows:
        if path == "decompose":
            result.append((agent_id, quality))
        elif path == "cfp":
            result.append((agent_id, quality * settings.CFP_COORDINATOR_CREDIT))
    return result


@dataclass
class AgentCreditHandler(EventHandler[TaskUpdatedEvent]):
    """Influence credit for all agents involved in a completed task.

    Fires on TaskUpdatedEvent when task status → "completed". Two credit paths run
    in a single DB session:

    ── Executor credit ────────────────────────────────────────────────────────────
    Agent that self-executed the task. Signal: score_outcome() quality score.
    Formula: EMA — new = base + 0.15 * (quality - base).
    Gate: event.state.execution_path == "self_execute" AND quality_score not None.

    ── Coordinator credit ─────────────────────────────────────────────────────────
    Agents that took a coordination action on the task (CFP routing, decomposition).
    Found via TaskExecution rows with execution_path IN ("cfp", "decompose").

    Two sub-cases depending on whether this event is for a root task or a subtask:

    Root task (parent_task_id is None):
      A task completing with quality_score set (self_execute path).
      Query delegation chain of THIS task → credit each agent proportionally.
      Handles CFP→Self-execute: CFP initiator gets partial, executor gets full.

    Subtask (parent_task_id is not None):
      Only credit when THIS is the last sibling to reach terminal status. At that
      point, compute avg quality across all completed sibling executions, then
      query the PARENT task's delegation chain and credit each agent.
      Handles pure decompose and CFP→Decompose chains.

    ── Why timing matters for decompose ───────────────────────────────────────────
    The parent task goes to "completed" immediately after decompose_and_publish()
    (via _finalise_execution), before any subtask executes. No quality signal
    exists at that moment. Coordinator credit therefore fires from the LAST subtask
    completion, not from the parent's completion event. This handler detects
    "last sibling" independently from RollupSubtaskHandler (different concern:
    credit vs. status propagation).

    ── Race condition (accepted) ──────────────────────────────────────────────────
    Concurrent completions for the same agent across different ARQ workers may
    produce lost-update races on agent.influence. Accepted for Phase 1 — influence
    is a soft EMA and one missed update is negligible. Phase 2 can add advisory
    locks or CAS if contention becomes measurable.

    ── Eventual consistency (accepted) ───────────────────────────────────────────
    If this handler fails after Phase 6 commits, the influence update for that task
    is lost. Accepted: strict atomicity would require execute_task to know about
    credit attribution, coupling job logic to the credit model.
    """

    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status") or event.state.status != "completed":
            return

        async with get_session() as session:
            await self._credit_executor(event, session)
            await self._credit_coordinator(event, session)

    async def _credit_executor(self, event: TaskUpdatedEvent, session: AsyncSession) -> None:
        if event.state.execution_path != "self_execute":
            return
        if event.state.executing_agent_id is None or event.state.quality_score is None:
            return

        agent_repo = AgentRepository(session)
        agent = await agent_repo.get_by_id(event.state.executing_agent_id)
        if agent is None:
            return

        agent.influence = compute_influence_ema(agent.influence, event.state.quality_score)
        await agent_repo.save(agent)
        session.add(  # raw — Gap 2
            InfluenceSnapshot(
                agent_id=agent.id,
                organisation_id=agent.organisation_id,
                workspace_id=agent.workspace_id,
                influence=agent.influence,
            )
        )
        logger.debug(
            "AgentCreditHandler executor: agent=%s influence=%.4f quality=%.3f",
            event.state.executing_agent_id,
            agent.influence,
            event.state.quality_score,
        )

    async def _credit_coordinator(self, event: TaskUpdatedEvent, session: AsyncSession) -> None:
        if event.state.parent_task_id is None:
            # Root task: credit delegation chain of this task directly.
            if event.state.quality_score is None:
                return
            credits = await compute_delegation_credits(
                event.state.id,
                event.state.workspace_id,
                event.state.quality_score,
                session,
            )
        else:
            # Subtask: credit parent's delegation chain when all siblings are done.
            credits = await self._subtask_rollup_credits(event, session)

        agent_repo = AgentRepository(session)
        for agent_id, quality_signal in credits:
            agent = await agent_repo.get_by_id(agent_id)
            if agent is None:
                continue
            agent.influence = compute_influence_ema(agent.influence, quality_signal)
            await agent_repo.save(agent)
            session.add(  # raw — Gap 2
                InfluenceSnapshot(
                    agent_id=agent.id,
                    organisation_id=agent.organisation_id,
                    workspace_id=agent.workspace_id,
                    influence=agent.influence,
                )
            )
            logger.debug(
                "AgentCreditHandler coordinator: agent=%s influence=%.4f signal=%.3f",
                agent_id,
                agent.influence,
                quality_signal,
            )

    async def _subtask_rollup_credits(
        self,
        event: TaskUpdatedEvent,
        session: AsyncSession,
    ) -> list[tuple[uuid.UUID, float]]:
        """Credit the parent task's delegation chain when this is the last sibling.

        Returns empty list if other siblings are still running or if no quality
        signal can be computed from completed siblings.
        """
        parent_id = event.state.parent_task_id
        workspace_id = event.state.workspace_id

        task_repo = TaskRepository(session)
        siblings = await task_repo.get_siblings(parent_id, workspace_id)

        if not siblings:
            return []
        if not all(TaskStateMachine.is_terminal(s.status) for s in siblings):
            return []  # more siblings still running — not the last one

        completed_ids = [s.id for s in siblings if s.status == "completed"]
        if not completed_ids:
            return []  # all siblings failed/expired — no quality signal

        avg_quality: float | None = (
            await session.execute(
                select(func.avg(TaskExecution.quality_score)).where(
                    TaskExecution.task_id.in_(completed_ids),
                    TaskExecution.status == "completed",
                )
            )
        ).scalar()

        if avg_quality is None:
            return []

        return await compute_delegation_credits(parent_id, workspace_id, avg_quality, session)
