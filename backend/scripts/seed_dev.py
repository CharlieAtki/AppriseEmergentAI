"""Dev bootstrap: creates org → user → workspace → API key and prints the raw key.

Run inside the api container:
    docker exec apprise-api-1 python /app/scripts/seed_dev.py

The raw API key is printed once — paste it into Swagger Authorize → ApiKeyAuth (X-API-Key).
Re-running creates a new API key against the same org/workspace (idempotent on structure).
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets

from core.database import get_session
from core.models.auth import ApiKey
from core.models.tenant import Organisation, OrganisationMember, User, Workspace
from sqlalchemy import select

_ORG_NAME = "Dev Org"
_CLERK_ORG_ID = "dev_org_local"
_CLERK_USER_ID = "dev_user_local"
_WORKSPACE_NAME = "Default"


async def main() -> None:
    async with get_session() as session:
        # Organisation
        result = await session.execute(
            select(Organisation).where(Organisation.clerk_org_id == _CLERK_ORG_ID)
        )
        org = result.scalar_one_or_none()
        if org is None:
            org = Organisation(clerk_org_id=_CLERK_ORG_ID, name=_ORG_NAME)
            session.add(org)
            await session.flush()

        # User
        result = await session.execute(select(User).where(User.clerk_user_id == _CLERK_USER_ID))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(clerk_user_id=_CLERK_USER_ID, email="dev@local", name="Dev User")
            session.add(user)
            await session.flush()

        # Membership
        result = await session.execute(
            select(OrganisationMember).where(
                OrganisationMember.organisation_id == org.id,
                OrganisationMember.user_id == user.id,
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(OrganisationMember(organisation_id=org.id, user_id=user.id, role="admin"))
            await session.flush()

        # Workspace
        result = await session.execute(
            select(Workspace).where(
                Workspace.organisation_id == org.id,
                Workspace.name == _WORKSPACE_NAME,
            )
        )
        workspace = result.scalar_one_or_none()
        if workspace is None:
            workspace = Workspace(organisation_id=org.id, name=_WORKSPACE_NAME)
            session.add(workspace)
            await session.flush()

        # API key (always creates a new one)
        import bcrypt as _bcrypt

        token = secrets.token_urlsafe(32)
        raw_key = f"apk_live_{token}"
        key_hash = _bcrypt.hashpw(raw_key.encode(), _bcrypt.gensalt()).decode()
        api_key = ApiKey(
            organisation_id=org.id,
            workspace_id=workspace.id,
            created_by_user_id=user.id,
            name="dev-seed-key",
            key_hash=key_hash,
            key_prefix=f"apk_live_{token[:8]}",
            key_sha256=hashlib.sha256(raw_key.encode()).hexdigest(),
            scopes=None,  # None = unrestricted; scoped keys require e.g. "tasks:write"
        )
        session.add(api_key)
        await session.flush()

    print()
    print("=" * 60)
    print(f"Workspace ID : {workspace.id}")
    print(f"API Key      : {raw_key}")
    print("=" * 60)
    print("Paste the API key into Swagger → Authorize → ApiKeyAuth.")
    print(f"Use workspace ID {workspace.id} in URL path parameters.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
