from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tenant import Organisation, OrganisationMember


class OrganisationRepository:
    """Identity lookup and lifecycle writes for Organisation and OrganisationMember.

    upsert()/upsert_member()/delete_by_external_id()/delete_member() are called
    exclusively by the Clerk webhook handler to keep Apprise's DB in sync with
    Clerk's identity data. get_by_id()/save() are general-purpose, used by any
    caller that already owns an org_id (e.g. the coordination-config service).

    Transaction contract: never calls commit() or flush() — callers own the transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, provider: str, external_id: str) -> Organisation | None:
        result = await self._session.execute(
            select(Organisation).where(
                Organisation.identity_provider == provider,
                Organisation.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, org_id: uuid.UUID) -> Organisation | None:
        """Unscoped PK lookup — caller already owns the ID (auth dep, worker path)."""
        return await self._session.get(Organisation, org_id)

    async def get_for_update(self, org_id: uuid.UUID) -> Organisation | None:
        """Fetch an Organisation with a row-level lock (SELECT ... FOR UPDATE).

        Used before a config (JSONB) read-modify-write — e.g. CoordinationConfigService —
        to prevent concurrent overwrites of unrelated keys. Mirrors
        AgentRepository.get_for_update's role for agent.skills."""
        return await self._session.get(Organisation, org_id, with_for_update=True)

    async def get_member(
        self, organisation_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganisationMember | None:
        """Composite-PK lookup — used by require_organisation() to read the caller's role."""
        return await self._session.get(OrganisationMember, (organisation_id, user_id))

    async def save(self, org: Organisation) -> None:
        """Re-stage after field mutations. No flush — session commits on exit."""
        self._session.add(org)

    async def upsert(self, provider: str, external_id: str, name: str | None) -> Organisation:
        stmt = (
            pg_insert(Organisation)
            .values(identity_provider=provider, external_id=external_id, name=name)
            .on_conflict_do_update(
                constraint="uq_organisations_provider_external_id",
                set_={"name": name},
            )
            .returning(Organisation)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def delete_by_external_id(self, provider: str, external_id: str) -> None:
        await self._session.execute(
            delete(Organisation).where(
                Organisation.identity_provider == provider,
                Organisation.external_id == external_id,
            )
        )

    async def upsert_member(
        self, organisation_id: uuid.UUID, user_id: uuid.UUID, role: str
    ) -> None:
        stmt = (
            pg_insert(OrganisationMember)
            .values(organisation_id=organisation_id, user_id=user_id, role=role)
            .on_conflict_do_update(
                constraint="organisation_members_pkey",
                set_={"role": role},
            )
        )
        await self._session.execute(stmt)

    async def delete_member(self, organisation_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(OrganisationMember).where(
                OrganisationMember.organisation_id == organisation_id,
                OrganisationMember.user_id == user_id,
            )
        )
