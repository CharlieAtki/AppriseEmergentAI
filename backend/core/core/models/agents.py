from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin
from core.models.tenant import Organisation, Workspace

if TYPE_CHECKING:
    from core.models.tasks import TaskExecution


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"

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
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("'active'"))
    skills: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    influence: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    __table_args__ = (sa.Index("ix_agents_workspace_id_status", "workspace_id", "status"),)

    organisation: Mapped[Organisation] = relationship()
    workspace: Mapped[Workspace] = relationship(back_populates="agents")
    task_executions: Mapped[list[TaskExecution]] = relationship(
        back_populates="agent",
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id} name={self.name!r} status={self.status!r}>"
