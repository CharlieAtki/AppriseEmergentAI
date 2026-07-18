from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

from core.coordination.contract_net import attempt_reservation, compute_bid_score
from core.coordination.task_state import TaskStateMachine

if TYPE_CHECKING:
    from arq import ArqRedis
    from core.models.agents import Agent
    from core.repositories.protocols import TaskRepositoryProtocol
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class Committable(Protocol):
    """Narrow interface for committing the caller's transaction — the only
    operation score_and_reserve needs beyond task_repo. Satisfied by
    AsyncSession without a wrapper."""

    async def commit(self) -> None: ...


async def score_and_reserve(
    task_repo: TaskRepositoryProtocol,
    session: Committable,
    agents: list[Agent],
    task_id: uuid.UUID,
    workspace_id: uuid.UUID,
    required_skills: Mapping[str, float] | None,
    domain_tags: Mapping[str, Any] | None,
    redis: Redis,
    arq_queue: ArqRedis,
) -> int:
    """Score agents, attempt reservation for the highest scorer, enqueue execute_task.

    Pure dispatch — no LLM, no extra DB reads beyond the agent roster the caller
    already loaded. Every candidate agent is scored and ranked; the top scorer
    always wins if the SETNX race succeeds — there is no minimum score to clear.
    Callers are responsible for the DB query and any agent exclusions (e.g.
    get_active_for_bidding already excludes agents with an in-flight task; CFP
    also excludes the initiating agent before calling this function).

    Returns the number of candidate agents scored, for caller-side observability.
    Falls through (returns 0) when there are no candidates, or completes with a
    non-zero count even if the reservation race is lost to another worker.
    """
    task_id_str = str(task_id)
    workspace_id_str = str(workspace_id)

    scored: list[tuple[Agent, float]] = [
        (
            agent,
            compute_bid_score(
                agent_skills=agent.skills or {},
                agent_influence=agent.influence or 0.0,
                required_skills=required_skills,
                agent_personality=agent.personality,
                task_domain_tags=domain_tags,
                task_id=task_id_str,
                agent_id=str(agent.id),
            ),
        )
        for agent in agents
    ]

    if not scored:
        return 0

    scored.sort(key=lambda x: x[1], reverse=True)
    for agent, score in scored:
        agent_id_str = str(agent.id)
        won = await attempt_reservation(redis, workspace_id_str, task_id_str, agent_id_str)
        if won:
            task = await task_repo.get_by_id(task_id)
            if task is None or task.status != "open":
                observed = "missing" if task is None else task.status
                logger.warning(
                    "task %s won by agent %s but not biddable (status=%s, workspace=%s) — releasing reservation",
                    task_id_str,
                    agent.id,
                    observed,
                    workspace_id_str,
                )
                await redis.delete(f"reservation:{workspace_id_str}:{task_id_str}")
                await redis.delete(f"agent_busy:{workspace_id_str}:{agent_id_str}")
            else:
                committed = False
                try:
                    TaskStateMachine.transition(task, "reserved")
                    await task_repo.save(task)
                    # Commit (not flush) — enqueue_job hands off to a worker that opens
                    # its own DB session; flush() only makes the row visible within this
                    # transaction, so a separate session would still see the pre-reservation
                    # status until this actually commits.
                    await session.commit()
                    committed = True
                    await arq_queue.enqueue_job(
                        "execute_task",
                        agent_id=agent_id_str,
                        task_id=task_id_str,
                        workspace_id=workspace_id_str,
                    )
                except Exception:
                    await redis.delete(f"reservation:{workspace_id_str}:{task_id_str}")
                    await redis.delete(f"agent_busy:{workspace_id_str}:{agent_id_str}")
                    if committed:
                        # enqueue_job failed after the reservation was already committed,
                        # so the earlier redis.delete() calls above freed the locks but
                        # can't undo that commit. Revert to "open" in a second transaction
                        # on the same session so the bus-level Retry wrapper's next attempt
                        # (worker/handlers/bidding.py, worker/handlers/cfp.py) can actually
                        # re-win this task instead of bouncing off task.status != "open"
                        # every time — without this, the retry loop is blind to this one
                        # failure mode and the task would sit orphaned until
                        # worker/jobs/sweep_tasks.py's stale-reservation sweep catches it,
                        # up to sweep_interval_minutes later. That sweep remains the
                        # backstop if this revert itself fails.
                        TaskStateMachine.transition(task, "open")
                        await task_repo.save(task)
                        await session.commit()
                    raise
                logger.info(
                    "task %s reserved by agent %s (score=%.3f, workspace=%s)",
                    task_id_str,
                    agent.id,
                    score,
                    workspace_id_str,
                )
            break

    return len(scored)
