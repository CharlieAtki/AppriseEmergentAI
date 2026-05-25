"""add execution_path to task_executions

Revision ID: 004
Revises: 003
Create Date: 2026-05-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_executions",
        sa.Column("execution_path", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_task_executions_execution_path",
        "task_executions",
        ["execution_path"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_executions_execution_path", table_name="task_executions")
    op.drop_column("task_executions", "execution_path")
