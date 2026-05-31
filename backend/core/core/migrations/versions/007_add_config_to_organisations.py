"""add config column to organisations

Revision ID: 007
Revises: 006
Create Date: 2026-05-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organisations", sa.Column("config", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("organisations", "config")