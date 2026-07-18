from __future__ import annotations

import math
import random
from collections.abc import Mapping, MutableSequence
from typing import TYPE_CHECKING, Any, Protocol

from redis.asyncio import Redis

from core.config import settings

if TYPE_CHECKING:
    from core.models.agents import Agent


class _Shuffler(Protocol):
    def shuffle(self, x: MutableSequence[Any]) -> None: ...


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


def compute_bid_score(
    agent_skills: Mapping[str, float],
    agent_influence: float,
    required_skills: Mapping[str, float],
    *,
    w_skill: float = settings.BID_W_SKILL,
    w_influence: float = settings.BID_W_INFLUENCE,
    influence_k: float = settings.BID_INFLUENCE_K,
) -> float:
    """Return a bid score in [0, 1] for an agent competing for a task.

    Pure function — no I/O, no async, no DB reads. Caller provides all state.
    Only ever called against agents already known to be idle (see
    AgentRepository.get_active_for_bidding and attempt_reservation's agent-level
    lock) — there is no capacity term because an agent with any active task is
    never a candidate in the first place.

    Components (default weights):
        skill_match      0.80 — how well agent skills cover required_skills
        influence_factor 0.20 — soft bias towards high-influence agents
    """
    skill = _skill_match(agent_skills, required_skills)
    influence = _influence_factor(agent_influence, influence_k)

    base = w_skill * skill + w_influence * influence

    return _clamp01(base)


def break_ties(
    scored: list[tuple[Agent, float]],
    rng: _Shuffler = random,
) -> list[tuple[Agent, float]]:
    """Sort scored agents descending, randomly shuffling agents tied for a score.

    Same top score → genuinely random pick, not a fixed hash-based tiebreak, so
    ties don't always resolve the same way for the same task/agent pair. Pure
    given rng — does not mutate the input list. rng defaults to the stdlib
    random module (same .shuffle() interface as random.Random) so callers can
    inject a seeded random.Random(n) for deterministic tests.
    """
    ranked = sorted(scored, key=lambda x: x[1], reverse=True)
    result = list(ranked)
    i = 0
    while i < len(ranked):
        j = i + 1
        while j < len(ranked) and ranked[j][1] == ranked[i][1]:
            j += 1
        if j - i > 1:
            group = result[i:j]
            rng.shuffle(group)
            result[i:j] = group
        i = j
    return result


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
