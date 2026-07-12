from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class UserWorkspaceDashboardLayout(Base, TimestampMixin):
    """A user's private observability dashboard for one workspace."""

    __tablename__ = "user_workspace_dashboard_layouts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    layout: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    active_page: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "workspace_id", name="uq_user_workspace_dashboard_layout"),
        sa.Index("ix_user_workspace_dashboard_layouts_workspace_id", "workspace_id"),
    )
