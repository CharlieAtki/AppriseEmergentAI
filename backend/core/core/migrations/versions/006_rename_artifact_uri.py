"""rename artifact_uri to artifact on task_executions

The column stores the literal text content of an agent's artifact output — a
plain str | None. The old name implied a dereferenceable file path or URI,
which was misleading.

Revision ID: 006
Revises: 005
Create Date: 2026-05-30
"""
from __future__ import annotations

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("task_executions", "artifact_uri", new_column_name="artifact")


def downgrade() -> None:
    op.alter_column("task_executions", "artifact", new_column_name="artifact_uri")