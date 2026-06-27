from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.repositories.org_repository import OrganisationRepository
from core.repositories.user_repository import UserRepository

_PROVIDER = "clerk"


@dataclass(frozen=True)
class ClerkWebhookEnvelope:
    type: str
    data: dict[str, Any]


class ClerkWebhookService:
    """Applies Clerk lifecycle events to the Apprise identity tables.

    Each method is idempotent — all writes use PostgreSQL upserts; deletes
    are no-ops when the row doesn't exist.

    Transaction contract: never calls commit() or flush() — the router commits.
    """

    def __init__(
        self,
        org_repo: OrganisationRepository,
        user_repo: UserRepository,
    ) -> None:
        self._org_repo = org_repo
        self._user_repo = user_repo

    async def handle(self, envelope: ClerkWebhookEnvelope) -> None:
        match envelope.type:
            case "organization.created":
                await self._org_created(envelope.data)
            case "organization.deleted":
                await self._org_deleted(envelope.data)
            case "user.created":
                await self._user_created(envelope.data)
            case "user.deleted":
                await self._user_deleted(envelope.data)
            case "organizationMembership.created":
                await self._membership_created(envelope.data)
            case "organizationMembership.deleted":
                await self._membership_deleted(envelope.data)
            case _:
                pass  # unknown event types silently accepted — see clerk-identity-sync.md

    async def _org_created(self, data: dict[str, Any]) -> None:
        await self._org_repo.upsert(
            provider=_PROVIDER,
            external_id=data["id"],
            name=data.get("name"),
        )

    async def _org_deleted(self, data: dict[str, Any]) -> None:
        await self._org_repo.delete_by_external_id(
            provider=_PROVIDER,
            external_id=data["id"],
        )

    async def _user_created(self, data: dict[str, Any]) -> None:
        email: str | None = None
        email_addresses = data.get("email_addresses") or []
        if email_addresses:
            email = email_addresses[0].get("email_address")

        first = data.get("first_name") or ""
        last = data.get("last_name") or ""
        name = f"{first} {last}".strip() or None

        await self._user_repo.upsert(
            provider=_PROVIDER,
            external_id=data["id"],
            email=email,
            name=name,
        )

    async def _user_deleted(self, data: dict[str, Any]) -> None:
        await self._user_repo.delete_by_external_id(
            provider=_PROVIDER,
            external_id=data["id"],
        )

    async def _membership_created(self, data: dict[str, Any]) -> None:
        org_external_id: str = data["organization"]["id"]
        user_external_id: str = data["public_user_data"]["user_id"]
        role: str = data.get("role", "member")

        org = await self._org_repo.get_by_external_id(_PROVIDER, org_external_id)
        user = await self._user_repo.get_by_external_id(_PROVIDER, user_external_id)

        if org is None or user is None:
            # Clerk guarantees org.created and user.created fire before membership events.
            # If either row is missing the event arrived severely out of order — skip it.
            return

        await self._org_repo.upsert_member(
            organisation_id=org.id,
            user_id=user.id,
            role=role,
        )

    async def _membership_deleted(self, data: dict[str, Any]) -> None:
        org_external_id: str = data["organization"]["id"]
        user_external_id: str = data["public_user_data"]["user_id"]

        org = await self._org_repo.get_by_external_id(_PROVIDER, org_external_id)
        user = await self._user_repo.get_by_external_id(_PROVIDER, user_external_id)

        if org is None or user is None:
            return

        await self._org_repo.delete_member(
            organisation_id=org.id,
            user_id=user.id,
        )
