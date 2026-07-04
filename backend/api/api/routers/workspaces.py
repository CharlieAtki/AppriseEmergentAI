from __future__ import annotations

import uuid

from core.models.tenant import Workspace
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from api.deps import (
    get_workspace_connections,
    get_workspace_observability_service,
    get_workspace_service,
    get_workspace_stream_service,
    require_stream_ticket,
    require_workspace,
)
from api.schemas.agent import AgentResponse
from api.schemas.workspace import (
    CreateWorkspaceRequest,
    StreamTicketResponse,
    UpdateWorkspaceRequest,
    WorkspaceMetricsResponse,
    WorkspaceResponse,
    WorkspaceStreamInitEvent,
)
from api.services.auth_service import WsTicketPayload
from api.services.workspace_observability_service import WorkspaceObservabilityService
from api.services.workspace_service import (
    CreateWorkspaceCommand,
    UpdateWorkspaceCommand,
    WorkspaceService,
)
from api.services.workspace_stream_service import WorkspaceStreamService
from api.ws.registry import WorkspaceConnectionRegistry

router = APIRouter()


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    request: Request,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    cmd = CreateWorkspaceCommand(
        org_id=request.state.auth.org_id,
        name=body.name,
        config=body.config,
    )
    ws = await service.create(cmd)
    return WorkspaceResponse.model_validate(ws)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    request: Request,
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[WorkspaceResponse]:
    org_id = request.state.auth.org_id
    workspaces = await service.list(org_id=org_id)
    return [WorkspaceResponse.model_validate(ws) for ws in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    request: Request,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    org_id = request.state.auth.org_id
    ws = await service.get(org_id=org_id, workspace_id=workspace_id)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return WorkspaceResponse.model_validate(ws)


@router.get("/{workspace_id}/metrics", response_model=WorkspaceMetricsResponse)
async def get_workspace_metrics(
    workspace: Workspace = Depends(require_workspace("read")),
    service: WorkspaceObservabilityService = Depends(get_workspace_observability_service),
) -> WorkspaceMetricsResponse:
    """The latest Workspace Metrics Snapshot — the routine periodic sample (Gini,
    specialisation index, agent count), distinct from an Emergence Event. See
    docs/backend/CONTEXT.md. 404 if sample_metrics hasn't run for this workspace yet
    (fewer than 2 active agents, or simply not enough time has passed)."""
    metrics = await service.get_latest_metrics(workspace.id)
    if metrics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No metrics yet")
    return WorkspaceMetricsResponse.model_validate(metrics)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    body: UpdateWorkspaceRequest,
    # workspace ORM provided by require_workspace() auth dep — passed directly to avoid a second DB read.
    workspace: Workspace = Depends(require_workspace("write")),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    cmd = UpdateWorkspaceCommand(
        name=body.name,
        status=body.status,
        result_webhook_url=body.result_webhook_url,
        webhook_secret=body.webhook_secret,
        config=body.config,
    )
    ws = await service.update(workspace, cmd)
    return WorkspaceResponse.model_validate(ws)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace: Workspace = Depends(require_workspace("write")),
    service: WorkspaceService = Depends(get_workspace_service),
) -> None:
    await service.delete(workspace)


@router.post("/{workspace_id}/stream-ticket", response_model=StreamTicketResponse)
async def mint_stream_ticket(
    workspace: Workspace = Depends(require_workspace("read")),
    service: WorkspaceStreamService = Depends(get_workspace_stream_service),
) -> StreamTicketResponse:
    """Single-use, 30s-TTL ticket for GET /{workspace_id}/stream.

    AuthMiddleware never runs for WebSocket scope, so the WS route can't verify a
    Clerk bearer token itself — this ordinary HTTP route mints a short-lived ticket
    under normal auth instead. See require_stream_ticket() in api/deps.py.
    """
    data = await service.mint_stream_ticket(workspace, workspace.organisation_id)
    return StreamTicketResponse.model_validate(data)


@router.websocket("/{workspace_id}/stream")
async def workspace_stream(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    _ticket: WsTicketPayload = Depends(require_stream_ticket),
    service: WorkspaceStreamService = Depends(get_workspace_stream_service),
    registry: WorkspaceConnectionRegistry = Depends(get_workspace_connections),
) -> None:
    """Live dashboard feed — init snapshot, then forwarded workspace:{id}:events.

    Client connects mid-session and gets no history by design (Redis Pub/Sub has
    none); the init payload below is the documented fix — a DB-backed snapshot of
    current state, then live events on top.
    """
    await websocket.accept()

    snapshot = await service.get_initial_snapshot(workspace_id)
    init_event = WorkspaceStreamInitEvent(
        agents=[AgentResponse.model_validate(agent) for agent in snapshot.agents],
        metrics=WorkspaceMetricsResponse.model_validate(snapshot.metrics)
        if snapshot.metrics is not None
        else None,
    )
    await websocket.send_text(init_event.model_dump_json())

    await registry.subscribe(workspace_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # browser sends nothing — detects disconnect only
    except WebSocketDisconnect:
        pass
    finally:
        await registry.unsubscribe(workspace_id, websocket)
