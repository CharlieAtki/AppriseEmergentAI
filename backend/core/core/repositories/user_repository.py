from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tenant import User


class UserRepository:
    """Read-only identity lookup for User.

    Used by validate_clerk_token() in auth_service to resolve an external provider ID
    to an internal UUID. No write methods — users are provisioned via the webhook
    flow, not via direct API calls.

    Transaction contract: never calls commit() or flush().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, provider: str, external_id: str) -> User | None:
        result = await self._session.execute(
            select(User).where(
                User.identity_provider == provider,
                User.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()
