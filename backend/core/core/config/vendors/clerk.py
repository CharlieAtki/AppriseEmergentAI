from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClerkConfig(BaseSettings):
    """Clerk authentication service configuration.

    Only consumed by the API process — the worker never verifies JWTs.
    An empty-string default prevents the worker from failing at startup
    when CLERK__SECRET_KEY is absent from its environment.

    Set CLERK__SECRET_KEY in .env (the double-underscore is the
    Pydantic-settings nested-prefix convention, matching ANTHROPIC__API_KEY).
    """

    model_config = SettingsConfigDict(env_prefix="CLERK__")

    secret_key: SecretStr = SecretStr("")
