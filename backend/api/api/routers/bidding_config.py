from __future__ import annotations

from core.models.tenant import Organisation, Workspace
from core.repositories.workspace_repository import WorkspaceRepository
from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_bidding_config_service,
    get_db,
    get_redis,
    get_workspace_repo,
    require_organisation,
    require_workspace,
)
from api.schemas.bidding_config import (
    BiddingConfigResponse,
    UpdateBiddingConfigRequest,
)
from api.services.bidding_config_service import (
    BiddingConfigService,
    SetBiddingOverrideCommand,
)

router = APIRouter()


@router.get("/organisations/{org_id}/bidding-config", response_model=BiddingConfigResponse)
async def get_org_bidding_config(
    org: Organisation = Depends(require_organisation("read")),
    service: BiddingConfigService = Depends(get_bidding_config_service),
) -> BiddingConfigResponse:
    data = await service.get_for_org(org)
    return BiddingConfigResponse.model_validate(data)


@router.patch("/organisations/{org_id}/bidding-config", response_model=BiddingConfigResponse)
async def update_org_bidding_config(
    body: UpdateBiddingConfigRequest,
    org: Organisation = Depends(require_organisation("write")),
    service: BiddingConfigService = Depends(get_bidding_config_service),
    # Same AsyncSession the service's repos use — FastAPI dedupes Depends(get_db).
    # Committed explicitly here so the org-level write is durable before this
    # handler returns, mirroring coordination_config.py's identical rationale.
    session: AsyncSession = Depends(get_db),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repo),
    redis: Redis = Depends(get_redis),
) -> BiddingConfigResponse:
    fields_set = body.model_fields_set
    cmd = SetBiddingOverrideCommand(
        bid_score_threshold=body.bid_score_threshold,
        bid_score_threshold_set="bid_score_threshold" in fields_set,
    )
    data = await service.set_org_override(org, cmd)
    await session.commit()
    # Same reasoning as coordination_config.py's org-level PATCH: an org
    # override affects every workspace under it, and the worker's cache key is
    # keyed per-workspace only (see worker/coordination/bidding.py's
    # _resolve_bidding_config), so invalidation must enumerate workspaces, not
    # delete a single org-keyed entry that nothing actually reads from.
    workspaces = await workspace_repo.list_all(org.id)
    if workspaces:
        await redis.delete(*(f"bidding_config:{ws.id}" for ws in workspaces))
    return BiddingConfigResponse.model_validate(data)


@router.get("/workspaces/{workspace_id}/bidding-config", response_model=BiddingConfigResponse)
async def get_workspace_bidding_config(
    workspace: Workspace = Depends(require_workspace("read")),
    service: BiddingConfigService = Depends(get_bidding_config_service),
) -> BiddingConfigResponse:
    data = await service.get_for_workspace(workspace)
    return BiddingConfigResponse.model_validate(data)


@router.patch("/workspaces/{workspace_id}/bidding-config", response_model=BiddingConfigResponse)
async def update_workspace_bidding_config(
    body: UpdateBiddingConfigRequest,
    # workspace ORM provided by require_workspace() auth dep — passed directly to avoid a second DB read.
    workspace: Workspace = Depends(require_workspace("write")),
    service: BiddingConfigService = Depends(get_bidding_config_service),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> BiddingConfigResponse:
    fields_set = body.model_fields_set
    cmd = SetBiddingOverrideCommand(
        bid_score_threshold=body.bid_score_threshold,
        bid_score_threshold_set="bid_score_threshold" in fields_set,
    )
    data = await service.set_workspace_override(workspace, cmd)
    await session.commit()
    # Invalidate after commit, not inside the service — invalidating before
    # commit risks the worker re-populating the cache from a session that
    # hasn't actually persisted yet.
    await redis.delete(f"bidding_config:{workspace.id}")
    return BiddingConfigResponse.model_validate(data)
