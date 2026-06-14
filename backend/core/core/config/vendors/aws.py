from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AWSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AWS__")

    region: str = "eu-west-2"
    access_key_id: SecretStr = SecretStr("")  # empty = rely on IAM role
    secret_access_key: SecretStr = SecretStr("")  # empty = rely on IAM role
    fast_model: str = "anthropic.claude-haiku-4-5-20251001-v1:0"
    strong_model: str = "anthropic.claude-sonnet-4-5-v1:0"
    # future: cloudwatch_log_group, sagemaker_endpoint
