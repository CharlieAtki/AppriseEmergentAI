"""add task provenance columns

Revision ID: 003
Revises: 002
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "coordinator_agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "created_by_agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "delegation_depth",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index("ix_tasks_coordinator_agent_id", "tasks", ["coordinator_agent_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_coordinator_agent_id", table_name="tasks")
    op.drop_column("tasks", "delegation_depth")
    op.drop_column("tasks", "created_by_agent_id")
    op.drop_column("tasks", "coordinator_agent_id")
