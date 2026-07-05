from __future__ import annotations

from core.intelligence.context import AgentContext, TaskEvaluationContext
from core.intelligence.prompts import evaluate


def _agent(influence_tier: str) -> AgentContext:
    return AgentContext(
        name="agent-1",
        skills={"python_coding": 0.9},
        influence=0.5,
        influence_tier=influence_tier,  # type: ignore[arg-type]
    )


def _task() -> TaskEvaluationContext:
    return TaskEvaluationContext(
        title="Refactor billing module",
        description="Split billing into smaller services",
        required_skills={"python_coding": 0.8},
        difficulty=4.0,
        domain_tags={"backend": 0.9},
        task_type="coding",
        delegation_depth=0,
        depth_exceeded=False,
    )


class TestBuildPrompt:
    def test_high_tier_guideline_present(self) -> None:
        messages = evaluate.build_prompt(_agent("high"), _task(), 4.0)
        system = messages[0]["content"]
        assert 'influence_tier is "high"' in system
        assert "act as a coordinator" in system

    def test_low_tier_guideline_present(self) -> None:
        messages = evaluate.build_prompt(_agent("low"), _task(), 4.0)
        system = messages[0]["content"]
        assert 'influence_tier is "low"' in system
        assert "build a track record" in system

    def test_user_message_reports_tier_and_raw_value(self) -> None:
        messages = evaluate.build_prompt(_agent("neutral"), _task(), 4.0)
        user = messages[1]["content"]
        assert "Influence tier: neutral (raw=0.50)" in user

    def test_cfp_guideline_notes_influence_independence(self) -> None:
        messages = evaluate.build_prompt(_agent("high"), _task(), 4.0)
        system = messages[0]["content"]
        assert "influence_tier does not affect this choice" in system

    def test_decompose_threshold_is_hard_constraint_with_resolved_value(self) -> None:
        messages = evaluate.build_prompt(_agent("neutral"), _task(), 3.5)
        system = messages[0]["content"]
        assert "decompose is only valid when difficulty >= 3.5" in system
        assert "Prefer decompose" not in system
