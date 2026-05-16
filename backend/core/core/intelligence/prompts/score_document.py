from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScoreDocumentResponse(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    strengths: list[str]
    weaknesses: list[str]


def build_prompt(task: dict[str, Any], document: str) -> list[dict]:
    system = (
        "You are an objective evaluator scoring a document produced by an AI agent.\n\n"
        "Score on four equally-weighted criteria (each 0.0–1.0, average = final score):\n"
        "  1. Completeness — does it address all parts of the task?\n"
        "  2. Accuracy     — is the content factually correct and well-reasoned?\n"
        "  3. Clarity      — is it well-structured and easy to understand?\n"
        "  4. Relevance    — does it stay on-topic without unnecessary padding?\n\n"
        "Be strict. A score above 0.8 should require genuinely strong work.\n\n"
        'Respond with JSON: {"score": 0.0–1.0, "reasoning": "...", '
        '"strengths": ["..."], "weaknesses": ["..."]}'
    )
    user = (
        f"Task: {task.get('title')}\n"
        f"Instructions: {task.get('description')}\n\n"
        f"Document to evaluate:\n{document}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(raw: str) -> ScoreDocumentResponse:
    return ScoreDocumentResponse.model_validate_json(raw)
