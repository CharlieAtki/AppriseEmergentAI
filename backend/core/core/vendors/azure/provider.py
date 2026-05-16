from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from core.config.vendors.azure import AzureConfig
from core.vendors.base import VendorProvider


class AzureProvider(VendorProvider):
    vendor_name = "azure"

    def __init__(self, config: AzureConfig) -> None:
        self._config = config

    def build_model(self, model_id: str, **kwargs: object) -> BaseChatModel:
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_deployment=model_id,
            azure_endpoint=self._config.endpoint,
            api_key=self._config.api_key.get_secret_value(),
            api_version=self._config.api_version,
            **kwargs,
        )
