from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class MemoryConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMORY__")

    qdrant_url: str = "http://localhost:6333"
    top_k: int = 5
    embedding_model: str = "BAAI/bge-small-en-v1.5"
