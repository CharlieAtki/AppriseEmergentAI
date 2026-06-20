from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class Model(Base, TimestampMixin):
    __tablename__ = "models"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    model_id: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(sa.Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )

    __table_args__ = (sa.Index("ix_models_vendor", "vendor"),)

    def __repr__(self) -> str:
        return (
            f"<Model model_id={self.model_id!r} vendor={self.vendor!r} is_active={self.is_active}>"
        )


class WorkspaceModelRouting(Base, TimestampMixin):
    __tablename__ = "workspace_model_routing"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:
        return f"<WorkspaceModelRouting workspace_id={self.workspace_id}>"
