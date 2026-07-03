from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tenant import User


class UserRepository:
    """Identity lookup and lifecycle writes for User.

    Write methods are called exclusively by the Clerk webhook handler to keep
    Apprise's DB in sync with Clerk's identity data.

    Transaction contract: never calls commit() or flush() — callers own the transaction.
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

    async def upsert(
        self, provider: str, external_id: str, email: str | None, name: str | None
    ) -> User:
        stmt = (
            pg_insert(User)
            .values(identity_provider=provider, external_id=external_id, email=email, name=name)
            .on_conflict_do_update(
                constraint="uq_users_provider_external_id",
                set_={"email": email, "name": name},
            )
            .returning(User)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def delete_by_external_id(self, provider: str, external_id: str) -> None:
        await self._session.execute(
            delete(User).where(
                User.identity_provider == provider,
                User.external_id == external_id,
            )
        )
