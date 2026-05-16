from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class OllamaConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OLLAMA__")

    base_url: str = "http://host.docker.internal:11434/v1"
    fast_model: str = "gemma4:e4b-instruct-q4_K_M"
    strong_model: str = "gemma4:27b-instruct-q4_K_M"
