"""add artifact_id and skill_tags_used to task_executions

Revision ID: 011
Revises: 010
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_executions",
        sa.Column(
            "artifact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "task_executions",
        sa.Column("skill_tags_used", ARRAY(sa.Text), nullable=True),
    )
    op.create_index("ix_task_executions_artifact_id", "task_executions", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_task_executions_artifact_id", table_name="task_executions")
    op.drop_column("task_executions", "skill_tags_used")
    op.drop_column("task_executions", "artifact_id")
