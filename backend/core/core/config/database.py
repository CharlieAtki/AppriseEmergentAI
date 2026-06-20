from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE__")

    url: str = ""
    pool_size: int = 10
    pool_timeout: int = 30
