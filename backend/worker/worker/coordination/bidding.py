from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from core.config import settings
from core.coordination.config import BiddingConfig, resolve_bidding_config
from core.coordination.contract_net import attempt_reservation, compute_bid_score
from core.coordination.task_state import TaskStateMachine
from core.repositories.org_repository import OrganisationRepository
from core.repositories.workspace_repository import WorkspaceRepository

if TYPE_CHECKING:
    from arq import ArqRedis
    from core.models.agents import Agent
    from core.repositories.protocols import TaskRepositoryProtocol
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Belt-and-braces fallback only — the API's PATCH routes invalidate this key on
# every write (see api/routers/bidding_config.py). The TTL guards against any
# future write path that forgets to invalidate, not normal operation. Mirrors
# execute_task.py's _COORDINATION_CONFIG_CACHE_TTL_SECONDS.
_BIDDING_CONFIG_CACHE_TTL_SECONDS = 300


async def _resolve_bidding_config(
    redis: Redis,
    session: AsyncSession,
    organisation_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> BiddingConfig:
    """Cache-then-DB resolution of this workspace's effective bid-scoring config.

    Called on every TaskCreatedStreamEvent/CfpIssuedStreamEvent — a hotter path
    than execute_task.py's per-task _resolve_coordination_config (once per task
    execution, not once per bidding round), so caching matters more here, not
    less. Never imports api/ — reads Organisation/Workspace directly via core/
    repositories, since the worker must not depend on the HTTP layer.
    """
    cache_key = f"bidding_config:{workspace_id}"
    cached = await redis.get(cache_key)
    if cached is not None:
        return BiddingConfig(**json.loads(cached))

    organisation = await OrganisationRepository(session).get_by_id(organisation_id)
    workspace = await WorkspaceRepository(session).get_by_id(workspace_id)

    org_override = (organisation.config or {}).get("bidding") if organisation else None
    workspace_override = (workspace.config or {}).get("bidding") if workspace else None
    bidding_cfg = resolve_bidding_config(settings.bidding, org_override, workspace_override)

    await redis.set(
        cache_key, json.dumps(asdict(bidding_cfg)), ex=_BIDDING_CONFIG_CACHE_TTL_SECONDS
    )
    return bidding_cfg


async def score_and_reserve(
    task_repo: TaskRepositoryProtocol,
    agents: list[Agent],
    task_id: uuid.UUID,
    workspace_id: uuid.UUID,
    required_skills: Mapping[str, float] | None,
    domain_tags: Mapping[str, Any] | None,
    redis: Redis,
    arq_queue: ArqRedis,
    bid_score_threshold: float,
) -> None:
    """Score agents, attempt reservation for the highest scorer, enqueue execute_task.

    Pure dispatch — no LLM, no extra DB reads beyond the agent roster the caller
    already loaded. Falls through silently when no agent meets the threshold or when
    another worker wins the SETNX race first.

    Callers are responsible for the DB query and any agent exclusions (e.g. CFP
    excludes the initiating agent before calling this function), and for resolving
    bid_score_threshold (see _resolve_bidding_config) — this function receives it
    as a plain value rather than resolving it itself, same convention as
    compute_bid_score() receiving resolved weights instead of reading settings.
    """
    task_id_str = str(task_id)
    workspace_id_str = str(workspace_id)

    scored: list[tuple[Agent, float]] = []
    for agent in agents:
        active = sum(1 for e in agent.task_executions if e.status == "executing")
        score = compute_bid_score(
            agent_skills=agent.skills or {},
            agent_influence=agent.influence or 0.0,
            agent_active_tasks=active,
            required_skills=required_skills,
            agent_personality=agent.personality,
            task_domain_tags=domain_tags,
            task_id=task_id_str,
            agent_id=str(agent.id),
        )
        if score >= bid_score_threshold:
            scored.append((agent, score))

    if not scored:
        return

    scored.sort(key=lambda x: x[1], reverse=True)
    for agent, score in scored:
        won = await attempt_reservation(redis, workspace_id_str, task_id_str, str(agent.id))
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
            else:
                try:
                    TaskStateMachine.transition(task, "reserved")
                    await task_repo.save(task)
                    await task_repo.flush()  # must precede enqueue_job — ensures task.id is committed before worker picks it up
                    await arq_queue.enqueue_job(
                        "execute_task",
                        agent_id=str(agent.id),
                        task_id=task_id_str,
                        workspace_id=workspace_id_str,
                    )
                except Exception:
                    await redis.delete(f"reservation:{workspace_id_str}:{task_id_str}")
                    raise
                logger.info(
                    "task %s reserved by agent %s (score=%.3f, workspace=%s)",
                    task_id_str,
                    agent.id,
                    score,
                    workspace_id_str,
                )
            break
