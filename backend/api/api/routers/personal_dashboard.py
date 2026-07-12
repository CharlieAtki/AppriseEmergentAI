from __future__ import annotations

import uuid

from core.models.tenant import Workspace
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, get_personal_dashboard_service, require_user_session, require_workspace
from api.schemas.personal_dashboard import (
    PersonalDashboardLayoutRequest,
    PersonalDashboardLayoutResponse,
)
from api.services.personal_dashboard_service import (
    PersonalDashboardLayoutData,
    PersonalDashboardService,
    SavePersonalDashboardLayoutCommand,
)

router = APIRouter()


def _response(data: PersonalDashboardLayoutData) -> PersonalDashboardLayoutResponse:
    return PersonalDashboardLayoutResponse(
        pages=data.pages,
        active_page=data.active_page,
        updated_at=data.updated_at,
    )


@router.get("/{workspace_id}/dashboard-layout", response_model=PersonalDashboardLayoutResponse)
async def get_personal_dashboard_layout(
    workspace: Workspace = Depends(require_workspace("read")),
    user_id: uuid.UUID = Depends(require_user_session),
    service: PersonalDashboardService = Depends(get_personal_dashboard_service),
) -> PersonalDashboardLayoutResponse:
    return _response(await service.get(user_id, workspace.id))


@router.put("/{workspace_id}/dashboard-layout", response_model=PersonalDashboardLayoutResponse)
async def save_personal_dashboard_layout(
    body: PersonalDashboardLayoutRequest,
    workspace: Workspace = Depends(require_workspace("read")),
    user_id: uuid.UUID = Depends(require_user_session),
    service: PersonalDashboardService = Depends(get_personal_dashboard_service),
    session: AsyncSession = Depends(get_db),
) -> PersonalDashboardLayoutResponse:
    data = await service.save(
        user_id,
        workspace.id,
        SavePersonalDashboardLayoutCommand(
            pages=body.model_dump(mode="json")["pages"], active_page=body.active_page
        ),
    )
    await session.commit()
    return _response(data)
