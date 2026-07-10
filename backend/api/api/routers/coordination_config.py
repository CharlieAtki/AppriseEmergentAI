from __future__ import annotations

from core.models.tenant import Organisation, Workspace
from core.repositories.workspace_repository import WorkspaceRepository
from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_coordination_config_service,
    get_db,
    get_redis,
    get_workspace_repo,
    require_organisation,
    require_workspace,
)
from api.schemas.coordination_config import (
    CoordinationConfigResponse,
    UpdateCoordinationConfigRequest,
)
from api.services.coordination_config_service import (
    CoordinationConfigService,
    SetCoordinationOverrideCommand,
)

router = APIRouter()


@router.get(
    "/organisations/{org_id}/coordination-config", response_model=CoordinationConfigResponse
)
async def get_org_coordination_config(
    org: Organisation = Depends(require_organisation("read")),
    service: CoordinationConfigService = Depends(get_coordination_config_service),
) -> CoordinationConfigResponse:
    data = await service.get_for_org(org)
    return CoordinationConfigResponse.model_validate(data)


@router.patch(
    "/organisations/{org_id}/coordination-config", response_model=CoordinationConfigResponse
)
async def update_org_coordination_config(
    body: UpdateCoordinationConfigRequest,
    org: Organisation = Depends(require_organisation("write")),
    service: CoordinationConfigService = Depends(get_coordination_config_service),
    # Same AsyncSession the service's repos use — FastAPI dedupes Depends(get_db).
    # Committed explicitly here (not left to get_db()'s auto-commit-on-teardown)
    # so the org-level write is durable before this handler returns.
    session: AsyncSession = Depends(get_db),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repo),
    redis: Redis = Depends(get_redis),
) -> CoordinationConfigResponse:
    fields_set = body.model_fields_set
    cmd = SetCoordinationOverrideCommand(
        max_delegation_depth=body.max_delegation_depth,
        max_delegation_depth_set="max_delegation_depth" in fields_set,
        decompose_difficulty_threshold=body.decompose_difficulty_threshold,
        decompose_difficulty_threshold_set="decompose_difficulty_threshold" in fields_set,
    )
    data = await service.set_org_override(org, cmd)
    await session.commit()
    # An org override affects every workspace under it — the worker's cache key
    # is keyed per-workspace only (see execute_task.py's _resolve_coordination_config),
    # so a single redis.delete(f"coordination_config:{org.id}") would invalidate
    # nothing real. Invalidate after commit, same ordering rationale as the
    # workspace-level PATCH below: invalidating before commit risks the worker
    # re-populating the cache from a session that hasn't actually persisted yet.
    workspaces = await workspace_repo.list_all(org.id)
    if workspaces:
        await redis.delete(*(f"coordination_config:{ws.id}" for ws in workspaces))
    return CoordinationConfigResponse.model_validate(data)


@router.get(
    "/workspaces/{workspace_id}/coordination-config", response_model=CoordinationConfigResponse
)
async def get_workspace_coordination_config(
    workspace: Workspace = Depends(require_workspace("read")),
    service: CoordinationConfigService = Depends(get_coordination_config_service),
) -> CoordinationConfigResponse:
    data = await service.get_for_workspace(workspace)
    return CoordinationConfigResponse.model_validate(data)


@router.patch(
    "/workspaces/{workspace_id}/coordination-config", response_model=CoordinationConfigResponse
)
async def update_workspace_coordination_config(
    body: UpdateCoordinationConfigRequest,
    # workspace ORM provided by require_workspace() auth dep — passed directly to avoid a second DB read.
    workspace: Workspace = Depends(require_workspace("write")),
    service: CoordinationConfigService = Depends(get_coordination_config_service),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> CoordinationConfigResponse:
    fields_set = body.model_fields_set
    cmd = SetCoordinationOverrideCommand(
        max_delegation_depth=body.max_delegation_depth,
        max_delegation_depth_set="max_delegation_depth" in fields_set,
        decompose_difficulty_threshold=body.decompose_difficulty_threshold,
        decompose_difficulty_threshold_set="decompose_difficulty_threshold" in fields_set,
    )
    data = await service.set_workspace_override(workspace, cmd)
    await session.commit()
    # Invalidate after commit, not inside the service (unlike ApiKeyService.revoke()) —
    # invalidating before commit risks the worker re-populating the cache from a
    # session that hasn't actually persisted yet.
    await redis.delete(f"coordination_config:{workspace.id}")
    return CoordinationConfigResponse.model_validate(data)
