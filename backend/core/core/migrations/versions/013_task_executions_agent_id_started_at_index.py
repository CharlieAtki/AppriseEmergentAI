"""add composite index on task_executions(agent_id, started_at)

Revision ID: 013
Revises: 012
Create Date: 2026-07-11

Supports the new agent task-timeline endpoint (APP-49), which filters
task_executions by agent_id + a started_at window on every dashboard
load. Previously only indexed on task_id and (workspace_id, completed_at).
"""

from __future__ import annotations

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_task_executions_agent_id_started_at",
        "task_executions",
        ["agent_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_executions_agent_id_started_at", table_name="task_executions")
