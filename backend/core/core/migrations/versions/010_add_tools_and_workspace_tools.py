"""add tools and workspace_tools tables

Revision ID: 010
Revises: 009
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tools",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("namespace", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("tool_type", sa.Text, nullable=False, server_default=sa.text("'platform'")),
        sa.Column("config_schema", JSONB, nullable=True),
        sa.Column("task_types", ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("namespace", "name", name="uq_tools_namespace_name"),
    )
    op.create_index("ix_tools_namespace_name", "tools", ["namespace", "name"])
    op.create_index("ix_tools_is_active", "tools", ["is_active"])

    op.create_table(
        "workspace_tools",
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "tool_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tools.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("config", JSONB, nullable=True),
        sa.Column(
            "enabled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_workspace_tools_workspace_id", "workspace_tools", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("workspace_tools")
    op.drop_table("tools")
