"""replace clerk_org_id/clerk_user_id with identity_provider + external_id

Revision ID: 012
Revises: 011
Create Date: 2026-06-27

Decouples the schema from Clerk by replacing the Clerk-specific columns with a
generic (identity_provider, external_id) pair. Existing rows are migrated to
identity_provider='clerk'. The unique constraint on each table moves from a
single-column constraint to a composite one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- organisations ---
    op.add_column("organisations", sa.Column("identity_provider", sa.Text(), nullable=True))
    op.add_column("organisations", sa.Column("external_id", sa.Text(), nullable=True))

    op.execute("UPDATE organisations SET identity_provider = 'clerk', external_id = clerk_org_id")

    op.alter_column("organisations", "identity_provider", nullable=False)
    op.alter_column("organisations", "external_id", nullable=False)

    op.drop_constraint("organisations_clerk_org_id_key", "organisations", type_="unique")
    op.create_unique_constraint(
        "uq_organisations_provider_external_id",
        "organisations",
        ["identity_provider", "external_id"],
    )
    op.drop_column("organisations", "clerk_org_id")

    # --- users ---
    op.add_column("users", sa.Column("identity_provider", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("external_id", sa.Text(), nullable=True))

    op.execute("UPDATE users SET identity_provider = 'clerk', external_id = clerk_user_id")

    op.alter_column("users", "identity_provider", nullable=False)
    op.alter_column("users", "external_id", nullable=False)

    op.drop_constraint("users_clerk_user_id_key", "users", type_="unique")
    op.create_unique_constraint(
        "uq_users_provider_external_id",
        "users",
        ["identity_provider", "external_id"],
    )
    op.drop_column("users", "clerk_user_id")


def downgrade() -> None:
    # --- users ---
    op.add_column("users", sa.Column("clerk_user_id", sa.Text(), nullable=True))
    op.execute("UPDATE users SET clerk_user_id = external_id WHERE identity_provider = 'clerk'")
    op.alter_column("users", "clerk_user_id", nullable=False)
    op.drop_constraint("uq_users_provider_external_id", "users", type_="unique")
    op.create_unique_constraint("users_clerk_user_id_key", "users", ["clerk_user_id"])
    op.drop_column("users", "external_id")
    op.drop_column("users", "identity_provider")

    # --- organisations ---
    op.add_column("organisations", sa.Column("clerk_org_id", sa.Text(), nullable=True))
    op.execute(
        "UPDATE organisations SET clerk_org_id = external_id WHERE identity_provider = 'clerk'"
    )
    op.alter_column("organisations", "clerk_org_id", nullable=False)
    op.drop_constraint("uq_organisations_provider_external_id", "organisations", type_="unique")
    op.create_unique_constraint("organisations_clerk_org_id_key", "organisations", ["clerk_org_id"])
    op.drop_column("organisations", "external_id")
    op.drop_column("organisations", "identity_provider")
