"""add key_sha256 to api_keys

Stores the SHA-256 hex digest of the raw API key at creation time so that
revoke_api_key() can immediately delete the Redis cache entry rather than
relying on the 5-minute TTL. The column is nullable to avoid breaking rows
created before this migration; those keys get eventual-consistency revocation
via the cache TTL as before.

Revision ID: 005
Revises: 004
Create Date: 2026-05-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("key_sha256", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "key_sha256")