from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class CoordinationPlatformDefaults(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COORDINATION__")

    max_delegation_depth_default: int = 3
    # Hard ceiling — org/workspace overrides may never exceed this. This is the
    # actual runaway-recursion safety net; unlike the difficulty threshold it
    # cannot be freely overridden. See core/coordination/config.py.
    max_delegation_depth_ceiling: int = 5
    decompose_difficulty_threshold_default: float = 4.0
