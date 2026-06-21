from __future__ import annotations

import uuid

from core.models.tenant import Workspace
from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis

from api.deps import get_api_key_service, get_redis, require_workspace
from api.schemas.api_key import ApiKeyCreatedResponse, ApiKeyResponse, CreateApiKeyRequest
from api.services.api_key_service import ApiKeyService, CreateApiKeyCommand

router = APIRouter()


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateApiKeyRequest,
    request: Request,
    workspace: Workspace = Depends(require_workspace("write")),
    service: ApiKeyService = Depends(get_api_key_service),
) -> ApiKeyCreatedResponse:
    user_id: uuid.UUID | None = getattr(request.state.auth, "user_id", None)
    cmd = CreateApiKeyCommand(
        organisation_id=workspace.organisation_id,
        workspace_id=workspace.id,
        created_by_user_id=user_id,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )
    key_data, raw_key = await service.create(cmd)
    return ApiKeyCreatedResponse(
        id=key_data.id,
        key=raw_key,
        key_prefix=key_data.key_prefix,
        name=key_data.name,
        scopes=key_data.scopes or [],
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    workspace: Workspace = Depends(require_workspace("read")),
    service: ApiKeyService = Depends(get_api_key_service),
) -> list[ApiKeyResponse]:
    records = await service.list(workspace_id=workspace.id)
    return [ApiKeyResponse.model_validate(r) for r in records]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    workspace: Workspace = Depends(require_workspace("write")),
    service: ApiKeyService = Depends(get_api_key_service),
    redis: Redis = Depends(get_redis),
) -> None:
    result = await service.revoke(workspace_id=workspace.id, key_id=key_id, redis=redis)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
