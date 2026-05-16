from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from core.config.vendors.aws import AWSConfig
from core.vendors.base import VendorProvider


class AWSProvider(VendorProvider):
    vendor_name = "aws"

    def __init__(self, config: AWSConfig) -> None:
        self._config = config

    def build_model(self, model_id: str, **kwargs: object) -> BaseChatModel:
        from langchain_aws import ChatBedrock

        credentials: dict = {}
        if self._config.access_key_id.get_secret_value():
            credentials = {
                "aws_access_key_id": self._config.access_key_id.get_secret_value(),
                "aws_secret_access_key": self._config.secret_access_key.get_secret_value(),
            }

        return ChatBedrock(
            model_id=model_id,
            region_name=self._config.region,
            **credentials,
            **kwargs,
        )
