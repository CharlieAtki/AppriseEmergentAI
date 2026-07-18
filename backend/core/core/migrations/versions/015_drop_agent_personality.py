"""drop agent personality column

APP-51: personality (a cosine-similarity term in bid scoring, weight 0.05) is
removed from the ContractNet bidding system for product credibility — it also
leaked into the agent's LLM system prompt. See core/coordination/contract_net.py.

Revision ID: 015
Revises: 014
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("agents", "personality")


def downgrade() -> None:
    op.add_column("agents", sa.Column("personality", JSONB(), nullable=True))
