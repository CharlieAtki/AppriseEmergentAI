from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from core.config.vendors.ollama import OllamaConfig
from core.vendors.base import VendorProvider


class OllamaProvider(VendorProvider):
    vendor_name = "ollama"

    def __init__(self, config: OllamaConfig) -> None:
        self._config = config

    def build_model(self, model_id: str, **kwargs: object) -> BaseChatModel:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model_id,
            base_url=self._config.base_url,
            **kwargs,
        )
