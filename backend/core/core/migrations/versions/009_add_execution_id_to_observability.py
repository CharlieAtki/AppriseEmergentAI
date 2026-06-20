"""add execution_id to skill_snapshots and procedural_knowledge_logs

Revision ID: 009
Revises: 008
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "skill_snapshots",
        sa.Column("execution_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "uq_skill_snapshots_execution_id",
        "skill_snapshots",
        ["execution_id"],
        unique=True,
        postgresql_where=sa.text("execution_id IS NOT NULL"),
    )

    op.add_column(
        "procedural_knowledge_logs",
        sa.Column("execution_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "uq_procedural_knowledge_logs_execution_id",
        "procedural_knowledge_logs",
        ["execution_id"],
        unique=True,
        postgresql_where=sa.text("execution_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_skill_snapshots_execution_id", table_name="skill_snapshots")
    op.drop_column("skill_snapshots", "execution_id")

    op.drop_index(
        "uq_procedural_knowledge_logs_execution_id", table_name="procedural_knowledge_logs"
    )
    op.drop_column("procedural_knowledge_logs", "execution_id")
