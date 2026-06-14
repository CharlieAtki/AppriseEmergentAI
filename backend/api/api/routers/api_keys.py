from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, get_redis, require_workspace
from api.schemas.api_key import ApiKeyCreatedResponse, ApiKeyResponse, CreateApiKeyRequest
from api.services.api_key_service import ApiKeyService

router = APIRouter()


def get_service(session: AsyncSession = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(session)


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateApiKeyRequest,
    request: Request,
    workspace=Depends(require_workspace("write")),
    service: ApiKeyService = Depends(get_service),
) -> ApiKeyCreatedResponse:
    user_id: uuid.UUID | None = getattr(request.state.auth, "user_id", None)
    record, raw_key = await service.create(workspace=workspace, user_id=user_id, body=body)
    return ApiKeyCreatedResponse(
        id=record.id,
        key=raw_key,
        key_prefix=record.key_prefix,
        name=record.name,
        scopes=record.scopes or [],
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    workspace=Depends(require_workspace("read")),
    service: ApiKeyService = Depends(get_service),
) -> list[ApiKeyResponse]:
    records = await service.list(workspace_id=workspace.id)
    return [ApiKeyResponse.model_validate(r) for r in records]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    workspace=Depends(require_workspace("write")),
    service: ApiKeyService = Depends(get_service),
    redis=Depends(get_redis),
) -> None:
    record = await service.get(workspace_id=workspace.id, key_id=key_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await service.revoke(key=record, redis=redis)
