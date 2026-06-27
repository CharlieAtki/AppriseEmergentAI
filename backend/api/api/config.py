from __future__ import annotations

from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    # Comma-separated list of origins allowed to make cross-origin requests.
    # Set via CORS_ORIGINS env var:
    #   CORS_ORIGINS=http://localhost:3000,https://app.apprise.io
    #
    # Default is empty — CORS middleware is not registered when unset.
    # Production deployments that handle CORS at the reverse proxy / edge layer
    # (nginx, ALB, Cloudflare) should leave this unset.
    origins: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [u.strip() for u in self.origins.split(",") if u.strip()]

    model_config = {"env_prefix": "CORS_"}


api_settings = ApiSettings()
