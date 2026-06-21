from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, CreatedAtMixin, TimestampMixin

if TYPE_CHECKING:
    from core.models.tenant import Workspace


class Tool(Base, TimestampMixin):
    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    namespace: Mapped[str] = mapped_column(
        sa.Text, nullable=False
    )  # "platform" | "mcp.{server_name}" | "custom"
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    category: Mapped[str] = mapped_column(sa.Text, nullable=False)  # ToolCategory enum value
    tool_type: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default=sa.text("'platform'")
    )  # "platform" | "mcp"
    config_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # JSON Schema — drives UI form rendering
    task_types: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")
    )  # empty = all task types
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )

    workspace_tools: Mapped[list[WorkspaceTool]] = relationship(
        "WorkspaceTool", back_populates="tool", cascade="all, delete-orphan"
    )

    __table_args__ = (sa.UniqueConstraint("namespace", "name", name="uq_tools_namespace_name"),)


class WorkspaceTool(Base, CreatedAtMixin):
    __tablename__ = "workspace_tools"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tools.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # workspace-specific config (API keys, scope, MCP URL/auth)
    enabled_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    tool: Mapped[Tool] = relationship("Tool", back_populates="workspace_tools")
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="tools")
