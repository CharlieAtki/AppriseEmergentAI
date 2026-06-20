from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from core.config.vendors.anthropic import AnthropicConfig
from core.vendors.base import VendorProvider


class AnthropicProvider(VendorProvider):
    vendor_name = "anthropic"

    def __init__(self, config: AnthropicConfig) -> None:
        self._config = config

    def build_model(self, model_id: str, **kwargs: object) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic

        if self._config.api_key is None:
            raise RuntimeError("ANTHROPIC__API_KEY is not configured")

        return ChatAnthropic(
            model=model_id,
            api_key=self._config.api_key.get_secret_value(),
            **kwargs,
        )
