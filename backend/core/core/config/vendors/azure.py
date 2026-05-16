from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AzureConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AZURE__")

    endpoint: str = ""
    api_key: SecretStr = SecretStr("")
    api_version: str = "2024-02-01"
    tenant_id: str = ""
    client_id: str = ""
    client_secret: SecretStr = SecretStr("")
    # future: cognitive_services_endpoint, governance_policy_url
