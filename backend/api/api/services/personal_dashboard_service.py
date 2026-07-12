from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.models.personal_dashboard import UserWorkspaceDashboardLayout
from core.repositories.personal_dashboard_repository import PersonalDashboardRepository


@dataclass(frozen=True)
class SavePersonalDashboardLayoutCommand:
    pages: list[list[dict[str, Any]]]
    active_page: int


@dataclass(frozen=True)
class PersonalDashboardLayoutData:
    pages: list[list[dict[str, Any]]]
    active_page: int
    updated_at: datetime | None

    @classmethod
    def default(cls) -> PersonalDashboardLayoutData:
        return cls(pages=[[]], active_page=0, updated_at=None)

    @classmethod
    def from_domain(cls, layout: UserWorkspaceDashboardLayout) -> PersonalDashboardLayoutData:
        pages = layout.layout.get("pages")
        if not isinstance(pages, list):
            return cls.default()
        return cls(pages=pages, active_page=layout.active_page, updated_at=layout.updated_at)


class PersonalDashboardService:
    """Owns personal dashboard layout defaults and persistence orchestration."""

    def __init__(self, repo: PersonalDashboardRepository) -> None:
        self._repo = repo

    async def get(self, user_id: uuid.UUID, workspace_id: uuid.UUID) -> PersonalDashboardLayoutData:
        stored = await self._repo.get(user_id, workspace_id)
        return (
            PersonalDashboardLayoutData.from_domain(stored)
            if stored
            else PersonalDashboardLayoutData.default()
        )

    async def save(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID, cmd: SavePersonalDashboardLayoutCommand
    ) -> PersonalDashboardLayoutData:
        stored = await self._repo.upsert(
            user_id=user_id,
            workspace_id=workspace_id,
            layout={"pages": cmd.pages},
            active_page=cmd.active_page,
        )
        return PersonalDashboardLayoutData.from_domain(stored)
