from __future__ import annotations

import os


class Settings:
    # ContractNet reservation
    RESERVATION_TTL_SECONDS: int = int(os.getenv("RESERVATION_TTL_SECONDS", "30"))

    # Bid formula weights (must sum to 1.0)
    BID_W_SKILL: float = float(os.getenv("BID_W_SKILL", "0.60"))
    BID_W_CAPACITY: float = float(os.getenv("BID_W_CAPACITY", "0.20"))
    BID_W_INFLUENCE: float = float(os.getenv("BID_W_INFLUENCE", "0.15"))
    BID_W_PERSONALITY: float = float(os.getenv("BID_W_PERSONALITY", "0.05"))

    # Bid formula parameters
    BID_MAX_PARALLEL_TASKS: int = int(os.getenv("BID_MAX_PARALLEL_TASKS", "3"))
    BID_INFLUENCE_K: float = float(os.getenv("BID_INFLUENCE_K", "2.0"))
    BID_ADD_JITTER: bool = os.getenv("BID_ADD_JITTER", "true").lower() == "true"

    # Skill and influence decay (used by worker cron jobs)
    SKILL_DECAY_RATE: float = float(os.getenv("SKILL_DECAY_RATE", "0.02"))
    INFLUENCE_EMA_ALPHA: float = float(os.getenv("INFLUENCE_EMA_ALPHA", "0.15"))


settings = Settings()
