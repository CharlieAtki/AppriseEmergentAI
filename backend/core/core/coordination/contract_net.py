from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from redis.asyncio import Redis

from core.config import settings


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _skill_match(
    agent_skills: Mapping[str, float],
    required_skills: Mapping[str, float],
) -> float:
    if not required_skills:
        return 0.5  # neutral bid when task has no skill requirements
    total_weight = sum(required_skills.values())
    if total_weight == 0.0:
        return 0.5
    weighted_sum = sum(
        required_skills[skill] * _clamp01(agent_skills.get(skill, 0.0)) for skill in required_skills
    )
    return weighted_sum / total_weight


def _influence_factor(influence: float, k: float) -> float:
    # Saturating curve: rewards influence without letting it dominate.
    # influence is treated as already in [0, inf); we clamp to [0, 1] before
    # applying so the formula is meaningful without normalisation.
    return 1.0 - math.exp(-k * _clamp01(influence))


def _cosine_similarity(a: Mapping[str, float], b: Mapping[str, float]) -> float:
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
    agent_personality: Mapping[str, Any] | None,
    task_domain_tags: Mapping[str, Any] | None,
) -> float:
    if not agent_personality or not task_domain_tags:
        return 0.5  # neutral when either side is absent
    # Cast values to float for cosine similarity; non-numeric keys are skipped.
    try:
        a = {k: float(v) for k, v in agent_personality.items()}
        b = {k: float(v) for k, v in task_domain_tags.items()}
    except TypeError, ValueError:
        return 0.5
    sim = _cosine_similarity(a, b)  # [-1, 1]
    return (sim + 1.0) / 2.0  # [0, 1]


def _seeded_jitter(task_id: str, agent_id: str) -> float:
    # Deterministic ±0.01 tiebreaker keyed on the (task, agent) pair.
    # Same inputs always produce the same jitter — reproducible, not random.
    raw = hash(f"{task_id}:{agent_id}") % 201  # 0..200
    return (raw - 100) / 10_000.0  # -0.01 .. +0.01


def compute_bid_score(
    agent_skills: Mapping[str, float],
    agent_influence: float,
    required_skills: Mapping[str, float],
    agent_personality: Mapping[str, Any] | None = None,
    task_domain_tags: Mapping[str, Any] | None = None,
    *,
    task_id: str | None = None,
    agent_id: str | None = None,
    w_skill: float = settings.BID_W_SKILL,
    w_influence: float = settings.BID_W_INFLUENCE,
    w_personality: float = settings.BID_W_PERSONALITY,
    influence_k: float = settings.BID_INFLUENCE_K,
    add_jitter: bool = settings.BID_ADD_JITTER,
) -> float:
    """Return a bid score in [0, 1] for an agent competing for a task.

    Pure function — no I/O, no async, no DB reads. Caller provides all state.
    Only ever called against agents already known to be idle (see
    AgentRepository.get_active_for_bidding and attempt_reservation's agent-level
    lock) — there is no capacity term because an agent with any active task is
    never a candidate in the first place.

    Components (default weights):
        skill_match      0.80 — how well agent skills cover required_skills
        influence_factor 0.15 — soft bias towards high-influence agents
        personality_fit  0.05 — alignment between agent personality and task domain
    """
    skill = _skill_match(agent_skills, required_skills)
    influence = _influence_factor(agent_influence, influence_k)
    personality = _personality_fit(agent_personality, task_domain_tags)

    base = w_skill * skill + w_influence * influence + w_personality * personality

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
    """Atomically claim a task reservation and an agent-busy lock via Redis SETNX.

    Exactly one caller receives True even with concurrent attempts. Also claims
    an agent-level lock so the same agent can never be reserved for two tasks
    at once — each agent runs one task at a time by design (see
    AgentRepository.get_active_for_bidding, which pre-filters busy agents as an
    optimization; this lock is the actual correctness guarantee). If the agent
    lock loses its race, the task lock is released so another agent can win it.
    The TTL prevents a crashed worker from holding either lock indefinitely.
    Keys are workspace-scoped to prevent cross-workspace collisions.
    """
    task_won = await redis.set(
        f"reservation:{workspace_id}:{task_id}",
        agent_id,
        nx=True,
        ex=ttl_seconds,
    )
    if task_won is None:
        return False

    agent_claimed = await redis.set(
        f"agent_busy:{workspace_id}:{agent_id}",
        task_id,
        nx=True,
        ex=ttl_seconds,
    )
    if agent_claimed is None:
        await redis.delete(f"reservation:{workspace_id}:{task_id}")
        return False

    return True
