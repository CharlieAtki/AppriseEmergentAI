from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class CentrifugoConfig(BaseSettings):
    """Centrifugo real-time messaging server configuration.

    Only consumed by the worker (publishes dashboard/trace events) and the API
    process (proxy callback auth) — never the browser directly.

    Set via CENTRIFUGO__HTTP_API_URL / CENTRIFUGO__HTTP_API_KEY /
    CENTRIFUGO__PROXY_SECRET in .env, matching the ANTHROPIC__API_KEY /
    CLERK__SECRET_KEY nested-prefix convention.
    """

    model_config = SettingsConfigDict(env_prefix="CENTRIFUGO__")

    http_api_url: str = "http://localhost:8001/api"
    http_api_key: SecretStr = SecretStr("")
    # Shared secret Centrifugo attaches to its connect/subscribe proxy callbacks —
    # verified by require_centrifugo_proxy_secret() in api/deps.py.
    proxy_secret: SecretStr = SecretStr("")
