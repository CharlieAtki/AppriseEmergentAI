from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS__")

    url: str = "redis://localhost:6379"
