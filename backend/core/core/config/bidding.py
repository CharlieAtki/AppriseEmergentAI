from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BiddingPlatformDefaults(BaseSettings):
    """Platform-wide defaults for ContractNet bid-scoring config.

    Kept in its own file with its own env_prefix, separate from
    CoordinationPlatformDefaults (core/config/coordination.py) — each
    BaseSettings subclass here is an operator-facing env-var namespace
    (env_prefix + field name = the actual env var), so merging two unrelated
    settings classes together would leak a naming collision into that public
    contract (e.g. COORDINATION__BID_SCORE_THRESHOLD_DEFAULT would misname a
    bidding value as a coordination one — exactly the confusion the comment on
    Settings' flat-constants block already warns about). Every other domain
    sub-config in core/config/ (database.py, memory.py, intelligence.py, ...)
    follows this same one-class-per-file convention; this isn't a new rule.

    The *resolver* for this config (resolve_bidding_config) intentionally does
    NOT get the same one-file-per-knob treatment — see core/coordination/config.py
    for why that's a different axis with a different answer.
    """

    model_config = SettingsConfigDict(env_prefix="BIDDING__")

    # Minimum score an agent's bid must clear to be eligible for a task. A
    # plain tuning knob, not a runaway-safety value like max_delegation_depth's
    # ceiling — no clamp/ceiling concept for this field anywhere in the stack.
    bid_score_threshold_default: float = 0.3
