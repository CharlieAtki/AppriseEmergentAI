from __future__ import annotations

import math
from typing import TYPE_CHECKING

from redis.asyncio import Redis

from core.config import settings

if TYPE_CHECKING:
    from core.coordination.decompose import BusProtocol
    from core.models.agents import Agent
    from core.models.tasks import Task


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _skill_match(
    agent_skills: dict[str, float],
    required_skills: dict[str, float],
) -> float:
    if not required_skills:
        return 0.5  # neutral bid when task has no skill requirements
    total_weight = sum(required_skills.values())
    if total_weight == 0.0:
        return 0.5
    weighted_sum = sum(
        required_skills[skill] * _clamp01(agent_skills.get(skill, 0.0))
        for skill in required_skills
    )
    return weighted_sum / total_weight


def _capacity_factor(active_tasks: int, max_parallel: int) -> float:
    if max_parallel <= 0:
        return 0.0
    return _clamp01(1.0 - active_tasks / max_parallel)


def _influence_factor(influence: float, k: float) -> float:
    # Saturating curve: rewards influence without letting it dominate.
    # influence is treated as already in [0, inf); we clamp to [0, 1] before
    # applying so the formula is meaningful without normalisation.
    return 1.0 - math.exp(-k * _clamp01(influence))


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _personality_fit(
    agent_personality: dict | None,
    task_domain_tags: dict | None,
) -> float:
    if not agent_personality or not task_domain_tags:
        return 0.5  # neutral when either side is absent
    # Cast values to float for cosine similarity; non-numeric keys are skipped.
    try:
        a = {k: float(v) for k, v in agent_personality.items()}
        b = {k: float(v) for k, v in task_domain_tags.items()}
    except (TypeError, ValueError):
        return 0.5
    sim = _cosine_similarity(a, b)  # [-1, 1]
    return (sim + 1.0) / 2.0  # [0, 1]


def _seeded_jitter(task_id: str, agent_id: str) -> float:
    # Deterministic ±0.01 tiebreaker keyed on the (task, agent) pair.
    # Same inputs always produce the same jitter — reproducible, not random.
    raw = hash(f"{task_id}:{agent_id}") % 201  # 0..200
    return (raw - 100) / 10_000.0  # -0.01 .. +0.01


def compute_bid_score(
    agent_skills: dict[str, float],
    agent_influence: float,
    agent_active_tasks: int,
    required_skills: dict[str, float],
    agent_personality: dict | None = None,
    task_domain_tags: dict | None = None,
    *,
    task_id: str | None = None,
    agent_id: str | None = None,
    w_skill: float = settings.BID_W_SKILL,
    w_capacity: float = settings.BID_W_CAPACITY,
    w_influence: float = settings.BID_W_INFLUENCE,
    w_personality: float = settings.BID_W_PERSONALITY,
    max_parallel: int = settings.BID_MAX_PARALLEL_TASKS,
    influence_k: float = settings.BID_INFLUENCE_K,
    add_jitter: bool = settings.BID_ADD_JITTER,
) -> float:
    """Return a bid score in [0, 1] for an agent competing for a task.

    Pure function — no I/O, no async, no DB reads. Caller provides all state.

    Components (default weights):
        skill_match     0.60  — how well agent skills cover required_skills
        capacity_factor 0.20  — how much headroom the agent has (in-memory)
        influence_factor 0.15 — soft bias towards high-influence agents
        personality_fit 0.05  — alignment between agent personality and task domain
    """
    skill = _skill_match(agent_skills, required_skills)
    capacity = _capacity_factor(agent_active_tasks, max_parallel)
    influence = _influence_factor(agent_influence, influence_k)
    personality = _personality_fit(agent_personality, task_domain_tags)

    base = (
        w_skill * skill
        + w_capacity * capacity
        + w_influence * influence
        + w_personality * personality
    )

    if add_jitter and task_id is not None and agent_id is not None:
        base += _seeded_jitter(task_id, agent_id)

    return _clamp01(base)


async def attempt_reservation(
    redis: Redis,
    workspace_id: str,
    task_id: str,
    agent_id: str,
    ttl_seconds: int = settings.RESERVATION_TTL_SECONDS,
) -> bool:
    """Atomically claim a task reservation via Redis SETNX.

    Exactly one caller receives True even with concurrent attempts.
    The TTL prevents a crashed worker from holding the reservation indefinitely.
    Key is workspace-scoped to prevent cross-workspace collisions.
    """
    acquired = await redis.set(
        f"reservation:{workspace_id}:{task_id}",
        agent_id,
        nx=True,
        ex=ttl_seconds,
    )
    return acquired is not None


async def issue_cfp(
    task: Task,
    initiating_agent: Agent,
    bus: BusProtocol,
) -> None:
    """Publish a Call for Proposals event on the bus.

    Subscribing agents bid algorithmically (compute_bid_score) via their bus
    subscriber. Full CFP resolution (bid collection timeout, winner selection,
    ARQ enqueue) is implemented in the worker once core/bus/ exists.
    """
    await bus.publish(
        f"cfp.{task.workspace_id}.issued",
        {
            "task_id": str(task.id),
            "workspace_id": str(task.workspace_id),
            "organisation_id": str(task.organisation_id),
            "initiating_agent_id": str(initiating_agent.id),
            "required_skills": task.required_skills or {},
            "difficulty": task.difficulty,
            "task_type": task.task_type,
            "domain_tags": task.domain_tags or {},
        },
    )
