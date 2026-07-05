from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.agents import Agent
from core.models.base import Base
from core.models.tenant import Workspace


class SkillSnapshot(Base):
    __tablename__ = "skill_snapshots"

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
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    skills: Mapped[dict] = mapped_column(JSONB, nullable=False)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("ix_skill_snapshots_agent_id_recorded_at", "agent_id", "recorded_at"),
        sa.Index(
            "uq_skill_snapshots_execution_id",
            "execution_id",
            unique=True,
            postgresql_where=sa.text("execution_id IS NOT NULL"),
        ),
    )

    agent: Mapped[Agent] = relationship()
    workspace: Mapped[Workspace] = relationship()

    def __repr__(self) -> str:
        return f"<SkillSnapshot id={self.id} agent={self.agent_id} recorded_at={self.recorded_at}>"


class InfluenceSnapshot(Base):
    __tablename__ = "influence_snapshots"

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
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    influence: Mapped[float] = mapped_column(sa.Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("ix_influence_snapshots_agent_id_recorded_at", "agent_id", "recorded_at"),
    )

    agent: Mapped[Agent] = relationship()
    workspace: Mapped[Workspace] = relationship()

    def __repr__(self) -> str:
        return f"<InfluenceSnapshot id={self.id} agent={self.agent_id} influence={self.influence}>"


class WorkspaceMetricsSnapshot(Base):
    __tablename__ = "workspace_metrics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index(
            "ix_workspace_metrics_snapshots_workspace_id_recorded_at", "workspace_id", "recorded_at"
        ),
    )

    workspace: Mapped[Workspace] = relationship()

    def __repr__(self) -> str:
        return f"<WorkspaceMetricsSnapshot id={self.id} workspace={self.workspace_id}>"


@dataclass(frozen=True)
class WorkspaceMetricsPayload:
    """The shape of WorkspaceMetricsSnapshot.metrics (JSONB) — single source of
    truth for both the writer (worker/jobs/sample_metrics.py) and the reader
    (api/services/workspace_observability_service.py). Lives in core/ because
    both processes need it (see CLAUDE.md's api/worker/core boundary rule) —
    previously the write side built this as a raw dict literal and the read
    side re-typed it separately, with nothing enforcing the two stayed in sync.
    """

    gini: float
    specialisation_index: float
    agent_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "gini": self.gini,
            "specialisation_index": self.specialisation_index,
            "agent_count": self.agent_count,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> WorkspaceMetricsPayload:
        return cls(
            gini=raw["gini"],
            specialisation_index=raw["specialisation_index"],
            agent_count=raw["agent_count"],
        )


class EmergenceEvent(Base):
    __tablename__ = "emergence_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    gini_coefficient: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    hub_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("ix_emergence_events_workspace_id_recorded_at", "workspace_id", "recorded_at"),
    )

    workspace: Mapped[Workspace] = relationship()
    hub_agent: Mapped[Agent | None] = relationship(foreign_keys=[hub_agent_id])

    def __repr__(self) -> str:
        return (
            f"<EmergenceEvent id={self.id} type={self.event_type!r} gini={self.gini_coefficient}>"
        )


class ProceduralKnowledgeLog(Base):
    __tablename__ = "procedural_knowledge_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(sa.Text, nullable=False)
    rule_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    vector_store_ref: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index(
            "uq_procedural_knowledge_logs_execution_id",
            "execution_id",
            unique=True,
            postgresql_where=sa.text("execution_id IS NOT NULL"),
        ),
    )

    workspace: Mapped[Workspace] = relationship()
    agent: Mapped[Agent] = relationship()

    def __repr__(self) -> str:
        return f"<ProceduralKnowledgeLog id={self.id} domain={self.domain!r} agent={self.agent_id}>"
