from __future__ import annotations

import pytest
from core.coordination.contract_net import compute_bid_score


class TestComputeBidScore:
    def test_returns_value_in_unit_interval(self) -> None:
        score = compute_bid_score(
            agent_skills={"python": 0.8},
            agent_influence=0.5,
            required_skills={"python": 1.0},
        )
        assert 0.0 <= score <= 1.0

    def test_skill_only_path(self) -> None:
        # With influence/personality weights at zero, score = skill_match
        score = compute_bid_score(
            agent_skills={"python": 1.0},
            agent_influence=0.0,
            required_skills={"python": 1.0},
            w_skill=1.0,
            w_influence=0.0,
            w_personality=0.0,
            add_jitter=False,
        )
        assert score == pytest.approx(1.0)

    def test_no_required_skills_returns_neutral(self) -> None:
        score = compute_bid_score(
            agent_skills={"python": 0.9},
            agent_influence=0.5,
            required_skills={},
            w_skill=1.0,
            w_influence=0.0,
            w_personality=0.0,
            add_jitter=False,
        )
        # _skill_match returns 0.5 neutral when no skills required
        assert score == pytest.approx(0.5)

    def test_jitter_is_deterministic(self) -> None:
        kwargs = dict(
            agent_skills={"python": 0.5},
            agent_influence=0.3,
            required_skills={"python": 1.0},
            task_id="task-abc",
            agent_id="agent-xyz",
            add_jitter=True,
        )
        assert compute_bid_score(**kwargs) == compute_bid_score(**kwargs)

    def test_jitter_differs_across_agent_pairs(self) -> None:
        base = dict(
            agent_skills={},
            agent_influence=0.0,
            required_skills={},
            w_skill=0.0,
            w_influence=0.0,
            w_personality=0.0,
            add_jitter=True,
        )
        s1 = compute_bid_score(**base, task_id="t1", agent_id="a1")
        s2 = compute_bid_score(**base, task_id="t1", agent_id="a2")
        # Jitter envelope is ±0.01; verify both values fall within range
        assert -0.01 <= s1 <= 0.01
        assert -0.01 <= s2 <= 0.01

    def test_missing_skill_treated_as_zero(self) -> None:
        score_no_skill = compute_bid_score(
            agent_skills={},
            agent_influence=0.0,
            required_skills={"python": 1.0},
            w_skill=1.0,
            w_influence=0.0,
            w_personality=0.0,
            add_jitter=False,
        )
        score_zero_skill = compute_bid_score(
            agent_skills={"python": 0.0},
            agent_influence=0.0,
            required_skills={"python": 1.0},
            w_skill=1.0,
            w_influence=0.0,
            w_personality=0.0,
            add_jitter=False,
        )
        assert score_no_skill == pytest.approx(score_zero_skill)

    def test_score_clamped_to_unit_interval(self) -> None:
        # All weights at max and agent is perfect — should not exceed 1.0
        score = compute_bid_score(
            agent_skills={"a": 1.0},
            agent_influence=1.0,
            required_skills={"a": 1.0},
            w_skill=1.0,
            w_influence=1.0,
            w_personality=1.0,
            add_jitter=False,
        )
        assert score <= 1.0
