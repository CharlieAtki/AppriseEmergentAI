"""add user workspace dashboard layouts

Revision ID: 014
Revises: 013
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_workspace_dashboard_layouts",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("layout", JSONB, nullable=False),
        sa.Column("active_page", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "workspace_id", name="uq_user_workspace_dashboard_layout"),
    )
    op.create_index(
        "ix_user_workspace_dashboard_layouts_workspace_id",
        "user_workspace_dashboard_layouts",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_table("user_workspace_dashboard_layouts")
