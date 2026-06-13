from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IntelligenceConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INTELLIGENCE__")

    llm_backend: Literal["anthropic", "azure", "aws", "local"] = "anthropic"
    max_concurrent_llm_calls: int = 5
    force_heuristic_fallback: bool = False
    max_graph_steps: int = 10
    hub_influence_threshold: float = 0.7
    routing: dict[str, str] = Field(
        default_factory=lambda: {
            "evaluate":       "anthropic/claude-haiku-4-5-20251001",
            "reflect":        "anthropic/claude-sonnet-4-6",
            "decompose":      "anthropic/claude-sonnet-4-5",
            "enrich":         "anthropic/claude-haiku-4-5-20251001",
            "curate_memory":  "anthropic/claude-haiku-4-5-20251001",
            "execute":        "anthropic/claude-sonnet-4-5",
        }
    )
