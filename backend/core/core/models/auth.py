from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, CreatedAtMixin
from core.models.tenant import Organisation, User, Workspace


class ApiKey(Base, CreatedAtMixin):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Nullable so a deleted user doesn't cascade-delete their keys
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # SHA-256 hex digest of the raw key, stored at creation so revocation can
    # immediately delete the Redis cache entry (apikey_valid:{key_sha256}).
    # Not sensitive — SHA-256 is one-way and cannot reconstruct the raw key.
    # Nullable to handle keys created before migration 005.
    key_sha256: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    scopes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))

    __table_args__ = (
        sa.Index("ix_api_keys_workspace_id", "workspace_id"),
        sa.Index("ix_api_keys_organisation_id", "organisation_id"),
    )

    organisation: Mapped[Organisation] = relationship()
    workspace: Mapped[Workspace] = relationship(back_populates="api_keys")
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id} prefix={self.key_prefix!r} revoked={self.revoked}>"