from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tenant import Organisation


class OrganisationRepository:
    """Read-only Clerk identity lookup for Organisation.

    Used by validate_clerk_token() in auth_service to resolve a Clerk org ID to an
    internal UUID. No write methods — organisations are provisioned via the Clerk
    webhook flow, not via direct API calls.

    Transaction contract: never calls commit() or flush().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_clerk_org_id(self, clerk_org_id: str) -> Organisation | None:
        result = await self._session.execute(
            select(Organisation).where(Organisation.clerk_org_id == clerk_org_id)
        )
        return result.scalar_one_or_none()
