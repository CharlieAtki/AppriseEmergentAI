from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.agents import Agent
from core.models.base import Base, CreatedAtMixin, TimestampMixin
from core.models.tasks import Task
from core.models.tenant import Organisation, Workspace


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"

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
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    artifact_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("'draft'"))
    storage_ref: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index("ix_artifacts_workspace_id_status", "workspace_id", "status"),
    )

    organisation: Mapped[Organisation] = relationship()
    workspace: Mapped[Workspace] = relationship(back_populates="artifacts")
    operations: Mapped[list[ArtifactOperation]] = relationship(
        back_populates="artifact",
        cascade="all, delete-orphan",
    )
    contributions: Mapped[list[ArtifactContribution]] = relationship(
        back_populates="artifact",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Artifact id={self.id} title={self.title!r} status={self.status!r}>"


class ArtifactOperation(Base):
    __tablename__ = "artifact_operations"

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
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("'pending'"))
    # UUIDs of other ArtifactOperations that must complete before this one can start
    depends_on: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.Index("ix_artifact_operations_artifact_id_status", "artifact_id", "status"),
        sa.Index("ix_artifact_operations_task_id", "task_id"),
    )

    artifact: Mapped[Artifact] = relationship(back_populates="operations")
    task: Mapped[Task] = relationship()
    assigned_agent: Mapped[Agent | None] = relationship(foreign_keys=[assigned_agent_id])
    contributions: Mapped[list[ArtifactContribution]] = relationship(
        back_populates="operation",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ArtifactOperation id={self.id} type={self.operation_type!r} status={self.status!r}>"


class ArtifactContribution(Base, CreatedAtMixin):
    __tablename__ = "artifact_contributions"

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
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("artifact_operations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_ref: Mapped[str] = mapped_column(sa.Text, nullable=False)
    contribution_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    artifact: Mapped[Artifact] = relationship(back_populates="contributions")
    operation: Mapped[ArtifactOperation] = relationship(back_populates="contributions")
    agent: Mapped[Agent] = relationship()

    def __repr__(self) -> str:
        return f"<ArtifactContribution id={self.id} type={self.contribution_type!r} quality={self.quality_score}>"