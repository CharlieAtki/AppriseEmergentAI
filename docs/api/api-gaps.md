# API — Implementation Gaps

The API structure (`main.py`, `deps.py`, routers, middleware, service layer, event bridge)
is scaffolded. The following tracks what has been closed and what remains, in the same
format as `coordination-gaps.md` and `event-bus-gaps.md`.

---

## Closed gaps

### ~~1. Root tasks invisible to worker bidding~~

**Gap:** The API had no `POST /workspaces/{id}/tasks` route, and no mechanism to publish
`task.created` to Redis Streams. Root tasks created from the outside world could never
reach the worker — bidding never started, tasks sat at `"pending"` forever.

**What was done:**

- `api/handlers/task_bridge.py` — `TaskCreatedRedisPublisher(EventHandler[TaskCreatedEvent])`.
  Registered on the API's in-process `EventBus` at lifespan. When `task_logger.created(task)`
  fires in the background task, this handler constructs a `TaskCreatedStreamEvent` from the
  snapshot and calls `RedisBus.apublish()` → `XADD stream:task`. The worker's
  `TaskStreamSubscriber` then picks it up for bidding.

- `api/routers/tasks.py` — Three endpoints following the service layer + dep-factory
  pattern from the reference codebase:
  - `POST /workspaces/{id}/tasks` → `202 Accepted` with `task_id`
  - `GET /workspaces/{id}/tasks/{task_id}` → `TaskResponse`
  - `GET /workspaces/{id}/tasks` → `list[TaskResponse]`

- `api/services/task_service.py` — `TaskService` encapsulates all ORM logic (create,
  get, list). Routers never touch SQLAlchemy directly.

- `api/schemas/task.py` — `CreateTaskRequest`, `TaskCreatedResponse`, `TaskResponse`.

- `api/middleware/auth.py` — `ApiKeyMiddleware` stub (see open gap 1 below).

- `api/deps.py` — `get_db()` async generator dep added alongside existing bus/logger deps.

- `api/main.py` — `RedisBus` created in lifespan, `TaskCreatedRedisPublisher` registered,
  `ApiKeyMiddleware` added, tasks router included at `/workspaces/{workspace_id}/tasks`.

**Task creation flow as implemented:**

```
POST /workspaces/{workspace_id}/tasks  (X-API-Key header)
  ↓ ApiKeyMiddleware: validates header → sets request.state.auth
  ↓ require_workspace("write"): resolves org_id from request.state
  ↓ TaskService.create(): writes Task (status="enriching"), flushes
  ↓ session.commit()
  ↓ BackgroundTasks.add_task(enrich_and_release, task_id, bus.apublish)
  → 202 {"task_id": "..."}

[Background task]
  ↓ fresh session: load Task, set status="open", commit
  ↓ task_logger.created(task)
      ↓ TaskCreatedEvent → EventBus → TaskCreatedRedisPublisher
          ↓ RedisBus.apublish(TaskCreatedStreamEvent) → XADD stream:task

[Worker]
  TaskStreamSubscriber → TaskBiddingHandler → attempt_reservation → execute_task
```

---

## Open gaps

### 1. API-key validation is a stub

**Gap:** `ApiKeyMiddleware` accepts any non-empty `X-API-Key` header and sets a hardcoded
`org_id` (`00000000-0000-0000-0000-000000000001`). No key is validated against the
database. Any caller with any non-empty header string passes authentication.

**Impact:** All endpoints are effectively unauthenticated. Multi-tenancy is not enforced —
every request runs as the same stub org.

**What is needed** (see Notion "Authentication, API Security & Secrets Management"):

1. `ApiKey` model in `core/models/` — `key_hash` (bcrypt), `key_prefix`, `workspace_id`,
   `org_id`, `scopes`, `revoked`, `expires_at`.
2. `validate_api_key(raw_key, redis, db)` in `core/` — SHA-256 hash → Redis cache lookup
   (`apikey_valid:{hash}`, TTL 5 min) → bcrypt validation against Postgres on miss.
3. `ApiKeyMiddleware` updated to call `validate_api_key`, set real `org_id` + `workspace_id`
   from the key record, and enforce `revoked` / `expires_at`.
4. Cache invalidation on revoke: `DELETE apikey_valid:{hash}` in the revoke endpoint.

Key security invariants from the Notion doc:
- Raw key shown once on creation, never stored — only the bcrypt hash.
- Key is workspace-scoped: `workspace_id` in the URL must match `workspace_id` on the key.
- Cache miss path must validate against Postgres, not skip validation.

---

### 2. Clerk JWT middleware for human users

**Gap:** `ApiKeyMiddleware` only handles `X-API-Key` (machine-to-machine). Human users
authenticating via the frontend (Clerk JWT in the `Authorization: Bearer` header) receive
a 401 — the middleware does not recognise the JWT path.

**What is needed:**

Extend `ApiKeyMiddleware.dispatch()` to branch on header type:

```python
if api_key := request.headers.get("X-API-Key"):
    payload = await validate_api_key(api_key, redis, db)
    request.state.auth = payload
else:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    claims = clerk.verify_token(token)   # local crypto — no network call
    request.state.auth = TokenPayload(
        org_id=claims["org_id"],
        user_id=claims["sub"],
        auth_type="user",
    )
```

`clerk.verify_token()` is a local cryptographic operation — it does not make a network
call on every request. Clerk's public signing keys are fetched once at startup and cached.
The `CLERK_SECRET_KEY` setting must be populated (`.env` locally, AWS Secrets Manager in
production).

`org_id` in Clerk JWTs is Clerk's org ID. Middleware must map it to the internal UUID
(look up `organisations.clerk_org_id = claims["org_id"]`).

---

### 3. `require_workspace` has no DB lookup or permission check

**Gap:** `require_workspace(permission)` in `routers/tasks.py` reads `org_id` from
`request.state.auth` and returns it alongside the path `workspace_id`. It does not:
- Verify the workspace exists.
- Verify the workspace belongs to the caller's org.
- Check that the caller has `permission` level access (`read` / `write`).

A caller can pass any `workspace_id` UUID in the URL and the route will proceed.

**What is needed:**

After auth middleware sets `request.state.auth` with a real `org_id`, `require_workspace`
should load the `Workspace` row and enforce ownership:

```python
def require_workspace(permission: str = "write"):
    async def dep(
        workspace_id: uuid.UUID,
        request: Request,
        session: AsyncSession = Depends(get_db),
    ) -> Workspace:
        auth = request.state.auth
        workspace = await session.get(Workspace, workspace_id)
        if workspace is None or workspace.organisation_id != auth["org_id"]:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if permission == "write" and not auth.get("can_write", True):
            raise HTTPException(status_code=403, detail="Insufficient permission")
        return workspace
    return dep
```

Routes then receive a `Workspace` model (not a dict), and `organisation_id` comes from
`workspace.organisation_id` — removing the stub org_id entirely.

---

### 4. Task enrichment is a stub

**Gap:** `enrich_and_release()` in `routers/tasks.py` transitions `"enriching"` → `"open"`
immediately with no enrichment. `required_skills`, `difficulty`, `task_type`, and
`domain_tags` remain `None` on every root task.

**Impact:** Bid scoring uses `_skill_match()` which returns `0.5` when `required_skills`
is empty — every agent bids equally on every task. Specialisation signals are absent from
root tasks. Only subtasks generated by `decompose_and_publish()` carry enrichment metadata
(the LLM fills them at decompose time).

**What is needed:**

Replace the stub body in `enrich_and_release()` with the enrichment pipeline from the
Notion "Backend Developer Reference":

1. **Rule-based fast path** — infer `task_type` and rough `required_skills` from title
   keywords and domain patterns. No LLM call. Should classify ~85% of tasks correctly.
2. **LLM escalation** — if confidence < 0.85, call `llm_router.complete()` with
   `CallType.ENRICH` and the `enrich.py` prompt. Parse `required_skills`, `difficulty`,
   `task_type`, `domain_tags` from the response.
3. Update the `Task` row and transition `"enriching"` → `"open"`.
4. Call `task_logger.created(task)` → Redis publish as now.

The `enrich.py` prompt (`core/intelligence/prompts/enrich.py`) and `CallType.ENRICH`
already exist. The rule-based fast path is the only new piece.

Note: enrichment is the one case where the API process makes an LLM call (documented
in CLAUDE.md). It runs in a `BackgroundTask` so the `202` response is never delayed.

---

### 5. No `POST /workspaces/{id}/tasks/batch` endpoint

**Gap:** The Notion "Backend Developer Reference" specifies bulk task ingestion (up to 100
tasks per request). No batch endpoint exists.

**What is needed:**

```python
class BatchCreateTaskRequest(BaseModel):
    tasks: list[CreateTaskRequest] = Field(..., max_length=100)

class BatchCreatedResponse(BaseModel):
    task_ids: list[uuid.UUID]
    rejected: list[dict]   # index + reason for any task that failed validation
```

`POST /workspaces/{id}/tasks/batch` — validates each task individually (collect errors
rather than fail-fast), writes all valid tasks in a single flush, commits once, schedules
`enrich_and_release` for each. Returns `202` with `task_ids` + any `rejected` entries.

---

### 6. No webhook delivery on task completion

**Gap:** The `WebhookDelivery` model and table exist (`core/models/tasks.py`). Nothing
writes to it. When a task completes in the worker, no HTTP callback is made to the
workspace's `webhook_url`.

**What is needed:**

A worker handler bound to `TaskUpdatedEvent` (status transition to `"completed"`):

```python
class WebhookDeliveryHandler(EventHandler[TaskUpdatedEvent]):
    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status") or event.after.status != "completed":
            return
        await arq_queue.enqueue_job("deliver_webhook", task_id=str(event.after.id), ...)
```

A new ARQ job `worker/jobs/deliver_webhook.py` — loads `TaskExecution`, signs the
payload, calls the workspace's `webhook_url` with exponential backoff, writes
`WebhookDelivery` rows. Retry logic and the signing secret are documented in the Notion
auth doc.

---

### 7. No routers for workspaces, agents, or metrics

**Gap:** The Notion "Backend Developer Reference" specifies four router files. Only
`tasks.py` exists. The remaining three are missing:

| Router | Endpoints |
|---|---|
| `workspaces.py` | `POST /workspaces`, `GET /workspaces`, `GET /workspaces/{id}`, `PATCH /workspaces/{id}`, `DELETE /workspaces/{id}` |
| `agents.py` | `GET /workspaces/{id}/agents`, `GET /workspaces/{id}/agents/{aid}`, `POST /workspaces/{id}/agents`, `PATCH /workspaces/{id}/agents/{aid}` |
| `metrics.py` | `GET /workspaces/{id}/metrics`, `GET /workspaces/{id}/emergence` |

These follow the same service layer + dep-factory pattern as `tasks.py`. `workspaces.py`
is the highest priority — workspace creation is required before any tasks can be created
(the `workspace_id` FK is not nullable).

---

### 8. No WebSocket live dashboard

**Gap:** `GET /workspaces/{id}/stream` (WebSocket) is specified in the Notion doc. It
sends a state snapshot on connect, then forwards `workspace:{id}:events` Pub/Sub messages
from Redis to the browser in real time. Not implemented.

**What is needed:**

- FastAPI WebSocket endpoint at `/workspaces/{id}/stream`.
- On connect: query current agent states and last metrics from Postgres, send snapshot.
- Subscribe to `workspace:{id}:events` Redis Pub/Sub channel.
- Forward each message to the connected client until disconnect.
- Clean up the subscription on disconnect — a leaked Redis subscription is a memory leak
  that compounds with workspace count (noted explicitly in the Notion doc).

---

## Summary

| Gap | Status |
|-----|--------|
| Root tasks invisible to worker bidding — `POST /tasks` + Redis bridge | ✅ Closed |
| API-key validation is a stub — no bcrypt, no Redis cache, hardcoded org_id | ⚠️ Open |
| Clerk JWT middleware for human users | ❌ Open |
| `require_workspace` has no DB lookup or permission check | ⚠️ Open — alongside gap 1/2 |
| Task enrichment is a stub — `required_skills` always `None` | ⚠️ Open |
| Bulk task ingestion (`POST /tasks/batch`) | ❌ Open |
| Webhook delivery on task completion | ❌ Open |
| Routers: `workspaces.py`, `agents.py`, `metrics.py` | ❌ Open |
| WebSocket live dashboard (`/workspaces/{id}/stream`) | ❌ Open |
