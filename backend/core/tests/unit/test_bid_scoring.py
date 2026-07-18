from __future__ import annotations

import random
from dataclasses import dataclass

import pytest
from core.coordination.contract_net import break_ties, compute_bid_score


class TestComputeBidScore:
    def test_returns_value_in_unit_interval(self) -> None:
        score = compute_bid_score(
            agent_skills={"python": 0.8},
            agent_influence=0.5,
            required_skills={"python": 1.0},
        )
        assert 0.0 <= score <= 1.0

    def test_skill_only_path(self) -> None:
        # With influence weight at zero, score = skill_match
        score = compute_bid_score(
            agent_skills={"python": 1.0},
            agent_influence=0.0,
            required_skills={"python": 1.0},
            w_skill=1.0,
            w_influence=0.0,
        )
        assert score == pytest.approx(1.0)

    def test_no_required_skills_returns_neutral(self) -> None:
        score = compute_bid_score(
            agent_skills={"python": 0.9},
            agent_influence=0.5,
            required_skills={},
            w_skill=1.0,
            w_influence=0.0,
        )
        # _skill_match returns 0.5 neutral when no skills required
        assert score == pytest.approx(0.5)

    def test_missing_skill_treated_as_zero(self) -> None:
        score_no_skill = compute_bid_score(
            agent_skills={},
            agent_influence=0.0,
            required_skills={"python": 1.0},
            w_skill=1.0,
            w_influence=0.0,
        )
        score_zero_skill = compute_bid_score(
            agent_skills={"python": 0.0},
            agent_influence=0.0,
            required_skills={"python": 1.0},
            w_skill=1.0,
            w_influence=0.0,
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
        )
        assert score <= 1.0

    def test_default_weights_sum_to_one(self) -> None:
        # Perfect skill, influence weight isolated to zero — score should approach
        # w_skill (0.80) exactly, confirming the personality term is gone rather
        # than silently capping scores below what the weights imply.
        score = compute_bid_score(
            agent_skills={"python": 1.0},
            agent_influence=0.0,
            required_skills={"python": 1.0},
        )
        assert score == pytest.approx(0.80, abs=1e-3)


@dataclass(frozen=True)
class _FakeAgent:
    id: str


class TestBreakTies:
    def test_empty_list_is_noop(self) -> None:
        assert break_ties([]) == []

    def test_single_element_is_noop(self) -> None:
        a = _FakeAgent("a1")
        assert break_ties([(a, 0.5)]) == [(a, 0.5)]

    def test_distinct_scores_sorted_descending_and_untouched_by_rng(self) -> None:
        a, b, c = _FakeAgent("a"), _FakeAgent("b"), _FakeAgent("c")
        scored = [(a, 0.2), (b, 0.9), (c, 0.5)]
        result = break_ties(scored, rng=random.Random(0))
        assert result == [(b, 0.9), (c, 0.5), (a, 0.2)]

    def test_does_not_mutate_input_list(self) -> None:
        a, b = _FakeAgent("a"), _FakeAgent("b")
        scored = [(a, 0.2), (b, 0.9)]
        original = list(scored)
        break_ties(scored, rng=random.Random(0))
        assert scored == original

    def test_tied_top_scores_shuffled_deterministically_with_seeded_rng(self) -> None:
        a, b, c = _FakeAgent("a"), _FakeAgent("b"), _FakeAgent("c")
        scored = [(a, 0.5), (b, 0.5), (c, 0.5)]

        result_seed_1 = break_ties(scored, rng=random.Random(1))
        result_seed_1_again = break_ties(scored, rng=random.Random(1))
        assert result_seed_1 == result_seed_1_again

        # Same seed reproduces the same order every time; a different seed can
        # reorder the tied group (not guaranteed, but overwhelmingly likely for
        # a 3-element permutation — this asserts the rng is actually consulted).
        orders = {
            tuple(agent.id for agent, _ in break_ties(scored, rng=random.Random(seed)))
            for seed in range(10)
        }
        assert len(orders) > 1

    def test_tie_group_only_contains_original_members(self) -> None:
        a, b, c, d = _FakeAgent("a"), _FakeAgent("b"), _FakeAgent("c"), _FakeAgent("d")
        scored = [(a, 0.5), (b, 0.9), (c, 0.5), (d, 0.5)]
        result = break_ties(scored, rng=random.Random(3))
        assert result[0] == (b, 0.9)
        assert {agent.id for agent, _ in result[1:]} == {"a", "c", "d"}
