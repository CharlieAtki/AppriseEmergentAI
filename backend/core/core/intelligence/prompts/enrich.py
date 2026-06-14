from __future__ import annotations

from pydantic import BaseModel


class EnrichResponse(BaseModel):
    required_skills: dict[str, float]
    difficulty: float
    task_type: str
    domain_tags: dict[str, float]


def build_prompt(title: str, description: str) -> list[dict]:
    system = (
        "You are enriching a task with structured metadata so agents can bid on it accurately.\n\n"
        "Fields to produce:\n"
        "  required_skills: dict of skill_name → importance weight [0.0, 1.0]. "
        "Use concise snake_case skill names (e.g. 'python_coding', 'data_analysis', 'technical_writing').\n"
        "  difficulty: float [1.0, 5.0]. 1 = trivial, 3 = moderate, 5 = expert-level.\n"
        "  task_type: one of 'coding', 'research', 'writing', 'analysis', 'coordination', 'general'.\n"
        "  domain_tags: dict of domain → relevance weight [0.0, 1.0] "
        "(e.g. {'backend': 0.9, 'security': 0.4}).\n\n"
        'Respond with JSON: {"required_skills": {}, "difficulty": 2.0, '
        '"task_type": "...", "domain_tags": {}}'
    )
    user = f"Task title: {title}\n\nTask description: {description}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(raw: str) -> EnrichResponse:
    from core.intelligence.prompts import strip_fences

    return EnrichResponse.model_validate_json(strip_fences(raw))
