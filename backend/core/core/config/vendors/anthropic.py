from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AnthropicConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANTHROPIC__")

    api_key: SecretStr | None = None
    fast_model: str = "claude-haiku-4-5-20251001"
    strong_model: str = "claude-sonnet-4-5"
