from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.agents import Agent
from core.models.base import Base, CreatedAtMixin, TimestampMixin
from core.models.tenant import Organisation, Workspace


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

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
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("'pending'"))
    priority: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    task_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    required_skills: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    domain_tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index("ix_tasks_workspace_id_status_created_at", "workspace_id", "status", "created_at"),
        sa.Index("ix_tasks_parent_task_id", "parent_task_id"),
        # Partial unique index: only enforced when idempotency_key is set
        sa.Index(
            "uq_tasks_workspace_idempotency_key",
            "workspace_id",
            "idempotency_key",
            unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        ),
    )

    organisation: Mapped[Organisation] = relationship()
    workspace: Mapped[Workspace] = relationship(back_populates="tasks")
    parent_task: Mapped[Task | None] = relationship(
        "Task",
        remote_side="Task.id",
        foreign_keys="Task.parent_task_id",
        back_populates="subtasks",
    )
    subtasks: Mapped[list[Task]] = relationship(
        "Task",
        foreign_keys="Task.parent_task_id",
        back_populates="parent_task",
    )
    executions: Mapped[list[TaskExecution]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} status={self.status!r}>"


class TaskExecution(Base):
    __tablename__ = "task_executions"

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
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    artifact_uri: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    tool_trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.Index("ix_task_executions_task_id", "task_id"),
        sa.Index("ix_task_executions_workspace_id_completed_at", "workspace_id", "completed_at"),
    )

    task: Mapped[Task] = relationship(back_populates="executions")
    agent: Mapped[Agent] = relationship(back_populates="task_executions")
    # One-to-one: one execution produces at most one delivery record
    webhook_delivery: Mapped[WebhookDelivery | None] = relationship(
        back_populates="task_execution",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<TaskExecution id={self.id} status={self.status!r} quality={self.quality_score}>"


class WebhookDelivery(Base, CreatedAtMixin):
    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    # Stable external dedupe key customers can use to check if they already processed this delivery
    delivery_id: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
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
    task_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("task_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("'pending'"))
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_http_status: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index(
            "ix_webhook_deliveries_workspace_status_next_attempt",
            "workspace_id",
            "status",
            "next_attempt_at",
        ),
    )

    task_execution: Mapped[TaskExecution] = relationship(back_populates="webhook_delivery")

    def __repr__(self) -> str:
        return f"<WebhookDelivery id={self.id} status={self.status!r} attempts={self.attempt_count}>"