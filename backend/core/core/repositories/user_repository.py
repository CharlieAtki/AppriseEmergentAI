from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tenant import User


class UserRepository:
    """Read-only Clerk identity lookup for User.

    Used by validate_clerk_token() in auth_service to resolve a Clerk user ID to an
    internal UUID. No write methods — users are provisioned via the Clerk webhook
    flow, not via direct API calls.

    Transaction contract: never calls commit() or flush().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_clerk_user_id(self, clerk_user_id: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.clerk_user_id == clerk_user_id)
        )
        return result.scalar_one_or_none()
