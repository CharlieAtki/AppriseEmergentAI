from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, CreatedAtMixin, TimestampMixin

if TYPE_CHECKING:
    from core.models.agents import Agent
    from core.models.artifacts import Artifact
    from core.models.auth import ApiKey
    from core.models.tasks import Task


class Organisation(Base, TimestampMixin):
    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    clerk_org_id: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # TODO: expose via PATCH /orgs/{org_id}/config — org-level model routing default (requires org admin role)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    workspaces: Mapped[list[Workspace]] = relationship(
        back_populates="organisation",
        cascade="all, delete-orphan",
    )
    members: Mapped[list[OrganisationMember]] = relationship(
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organisation id={self.id} name={self.name!r}>"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    clerk_user_id: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    memberships: Mapped[list[OrganisationMember]] = relationship(
        back_populates="user",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


class OrganisationMember(Base, CreatedAtMixin):
    __tablename__ = "organisation_members"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("organisations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(sa.Text, nullable=False)

    __table_args__ = (
        sa.Index("ix_organisation_members_user_id", "user_id"),
    )

    organisation: Mapped[Organisation] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")

    def __repr__(self) -> str:
        return f"<OrganisationMember org={self.organisation_id} user={self.user_id} role={self.role!r}>"


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

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
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("'active'"))
    # General workspace settings (decay rates, quotas, agent count, etc.).
    # Model routing overrides live in workspace_model_routing — not here.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_webhook_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index("ix_workspaces_organisation_id", "organisation_id"),
    )

    organisation: Mapped[Organisation] = relationship(back_populates="workspaces")
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    agents: Mapped[list[Agent]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list[Task]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Workspace id={self.id} name={self.name!r} status={self.status!r}>"