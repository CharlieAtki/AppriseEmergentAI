"""Dev bootstrap: creates org → user → workspace → API key and prints the raw key.

Run inside the api container:
    docker exec apprise-api-1 python /app/scripts/seed_dev.py \
        --clerk-user-id user_2abc... \
        --clerk-org-id org_2xyz...

Clerk IDs must match the JWT your Clerk app will issue. Find them in the Clerk
dashboard under Users and Organizations after signing up via the frontend.

Re-running with the same IDs is idempotent on structure (org/user/workspace are
reused). A new API key is always created.

Identity provider is always "clerk" for this script. To seed other providers,
pass --provider <name> alongside the external IDs.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import secrets

from core.database import get_session
from core.models.auth import ApiKey
from core.models.tenant import Organisation, OrganisationMember, User, Workspace
from sqlalchemy import select

_ORG_NAME = "Dev Org"
_WORKSPACE_NAME = "Default"


async def main(clerk_org_id: str, clerk_user_id: str, provider: str = "clerk") -> None:
    async with get_session() as session:
        # Organisation
        result = await session.execute(
            select(Organisation).where(
                Organisation.identity_provider == provider,
                Organisation.external_id == clerk_org_id,
            )
        )
        org = result.scalar_one_or_none()
        if org is None:
            org = Organisation(identity_provider=provider, external_id=clerk_org_id, name=_ORG_NAME)
            session.add(org)
            await session.flush()

        # User
        result = await session.execute(
            select(User).where(
                User.identity_provider == provider,
                User.external_id == clerk_user_id,
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                identity_provider=provider,
                external_id=clerk_user_id,
                email="dev@local",
                name="Dev User",
            )
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
            scopes=None,
        )
        session.add(api_key)
        await session.flush()

    print()
    print("=" * 60)
    print(f"Provider     : {provider}")
    print(f"Org ID       : {clerk_org_id}")
    print(f"User ID      : {clerk_user_id}")
    print(f"Workspace ID : {workspace.id}")
    print(f"API Key      : {raw_key}")
    print("=" * 60)
    print("Paste the API key into Swagger → Authorize → ApiKeyAuth.")
    print(f"Use workspace ID {workspace.id} in URL path parameters.")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed dev org/user/workspace")
    parser.add_argument(
        "--clerk-user-id",
        required=True,
        help="External user ID from the identity provider (e.g. user_2abc... for Clerk)",
    )
    parser.add_argument(
        "--clerk-org-id",
        required=True,
        help="External org ID from the identity provider (e.g. org_2xyz... for Clerk)",
    )
    parser.add_argument(
        "--provider",
        default="clerk",
        help="Identity provider name (default: clerk)",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            clerk_org_id=args.clerk_org_id, clerk_user_id=args.clerk_user_id, provider=args.provider
        )
    )
