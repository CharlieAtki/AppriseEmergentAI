# API — Reference

The FastAPI process is the only HTTP entry point for the platform. It validates requests,
writes to Postgres, and enqueues work — it never runs agent logic or LangGraph graphs (the
one exception is task enrichment, which runs as a background task; see below).

---

## Architecture overview

```
Client
  │  X-API-Key or Authorization: Bearer <jwt>
  ▼
AuthMiddleware             resolves caller identity → request.state.auth
  │
  ▼
require_workspace dep      loads Workspace from DB, verifies org ownership + active status
  │
  ▼
Router                     validates request body, calls service
  │
  ▼
Service                    ORM writes, key generation, enrichment orchestration
  │
  ▼
Postgres                   source of truth

[Background]
BackgroundTasks → enrich_and_release → LLMRouter (optional) → XADD stream:task → Worker
```

**SoC invariant:** Routers validate and delegate. Services own all ORM logic. Middleware only
resolves identity. No business logic in middleware or routers.

---

## Authentication

Every request must carry one of two headers. Unauthenticated requests return `401`.

### API Key (`X-API-Key`)

For scripts, pipelines, and MCP clients. Keys are workspace-scoped.

**Validation flow:**

1. SHA-256 of the raw key → check Redis cache (`apikey_valid:{sha256}`, 5-min TTL).
2. Cache hit → deserialise `ApiKeyPayload`, skip to step 5.
3. Cache miss → query `api_keys WHERE key_prefix = ? AND revoked = false`. `key_prefix` is
   `f"appr_{raw_key[:8]}"` — narrows the DB scan to near-zero rows.
4. Loop candidates with `bcrypt.verify(raw_key, candidate.key_hash)`. bcrypt is not
   deterministic so you cannot query by hash — the prefix narrows, bcrypt confirms.
5. Check `expires_at`. If expired, return 401.
6. Cache the result for 300s. Background-update `last_used_at`.
7. Set `request.state.auth = ApiKeyPayload(workspace_id, org_id, scopes)`.

**Revocation** takes effect immediately: `DELETE` endpoint sets `revoked=True` in Postgres
and deletes `apikey_valid:{sha256}` from Redis, bypassing the TTL.

**Key generation** (at creation time):
```python
raw_key    = secrets.token_urlsafe(32)   # shown once, never stored
key_hash   = bcrypt.hash(raw_key)        # stored in Postgres
key_prefix = f"appr_{raw_key[:8]}"      # stored; shown in UI for identification
```

### Bearer JWT (Clerk)

For human users authenticating via the frontend. `clerk.verify_token(bearer)` is local
cryptographic verification against Clerk's public keys cached at startup — no network call
per request.

**Status:** Clerk org_id → internal UUID mapping is a TODO stub (see `api-gaps.md` open gap 1).

---

## Dependency chain

```
get_db()                → async generator, yields AsyncSession, commits on exit
get_redis()             → request.app.state.redis (Redis.asyncio client)
get_llm_router()        → request.app.state.llm_router (LLMRouter)
get_bus()               → request.app.state.bus (in-process EventBus)
get_event_publisher()   → bus.apublish (PublishFn)
get_task_activity_logger() → TaskActivityLogger(publish)
require_workspace(perm) → Workspace ORM model (verifies ownership, active status, scopes)
```

`get_db` and `get_service` share the same session within a request (FastAPI dep caching).
Routes never hold a session reference — they call service methods.

---

## Lifespan

On startup:
1. `EventBus` created; `RedisBus` connected.
2. `Redis` client connected (`app.state.redis`).
3. `core.vendors.anthropic` imported → self-registers models into `registry`.
4. `LLMRouter` built with `AnthropicProvider`, routing from `settings.intelligence.routing`,
   capped at 2 concurrent enrichment calls.
5. `TaskCreatedRedisPublisher` bound on `TaskCreatedEvent` → publishes to Redis Streams.

On shutdown: Redis clients closed, `bus.drain_pending()` awaited.

---

## Routes

### Workspaces

| Method | Path | Auth | Response |
|--------|------|------|----------|
| `POST` | `/workspaces` | any | `201 WorkspaceResponse` |
| `GET` | `/workspaces` | any | `200 list[WorkspaceResponse]` |
| `GET` | `/workspaces/{id}` | any | `200 WorkspaceResponse` |
| `PATCH` | `/workspaces/{id}` | write | `200 WorkspaceResponse` |
| `DELETE` | `/workspaces/{id}` | write | `204` |

`org_id` comes from `request.state.auth.org_id` — no explicit field needed in the request body.

`PATCH` accepts: `name`, `status` (`active / paused / archived`), `result_webhook_url`,
`webhook_secret`, `config`. Setting `result_webhook_url` is how customers register a delivery
endpoint for task results.

---

### Agents

| Method | Path | Auth | Response |
|--------|------|------|----------|
| `POST` | `/workspaces/{id}/agents` | write | `201 AgentResponse` |
| `GET` | `/workspaces/{id}/agents` | read | `200 list[AgentResponse]` |
| `GET` | `/workspaces/{id}/agents/{aid}` | read | `200 AgentResponse` |
| `PATCH` | `/workspaces/{id}/agents/{aid}` | write | `200 AgentResponse` |

Agents are created with `status="active"`. The worker updates `skills` and `influence`
autonomously after each task execution — the API only seeds the initial state and allows
`name` / `status` updates.

---

### API Keys

| Method | Path | Auth | Response |
|--------|------|------|----------|
| `POST` | `/workspaces/{id}/api-keys` | write | `201 ApiKeyCreatedResponse` |
| `GET` | `/workspaces/{id}/api-keys` | read | `200 list[ApiKeyResponse]` |
| `DELETE` | `/workspaces/{id}/api-keys/{kid}` | write | `204` |

`ApiKeyCreatedResponse` includes `key` — the raw plaintext key. This is the **only time**
the raw key is returned. It is not stored in Postgres (only the bcrypt hash is).

`ApiKeyResponse` never includes the hash or the raw key — only `key_prefix`, metadata, and
`revoked` status.

---

### Tasks

| Method | Path | Auth | Response |
|--------|------|------|----------|
| `POST` | `/workspaces/{id}/tasks` | write | `202 TaskCreatedResponse` |
| `GET` | `/workspaces/{id}/tasks/{tid}` | read | `200 TaskResponse` |
| `GET` | `/workspaces/{id}/tasks` | read | `200 list[TaskResponse]` |

**Request validation (`CreateTaskRequest`):**
- `description`: if provided, must be ≥ 10 characters.
- `deadline_at`: if provided, must be in the future.
- `priority`: if provided, must be `low / normal / high / critical`.
- `idempotency_key`: if provided and a task with the same `(workspace_id, idempotency_key)`
  already exists, the existing task is returned without creating a duplicate.

**`202` response includes:** `task_id`, `status` (`"enriching"`), `workspace_id`.

---

## Task creation flow

```
POST /workspaces/{workspace_id}/tasks  (X-API-Key header)
  │
  ├─ AuthMiddleware: validates key → ApiKeyPayload → request.state.auth
  ├─ require_workspace("write"): loads Workspace, verifies org + active + scopes
  ├─ TaskService.create(): inserts Task (status="enriching"), flushes
  ├─ TaskService.commit(): makes row durable
  └─ BackgroundTasks.add_task(enrich_and_release, task.id, bus.apublish, llm_router)
  → 202 {"task_id": "...", "status": "enriching", "workspace_id": "..."}

[Background task — enrich_and_release]
  ├─ enrich_rule_based(title, description)
  │    ├─ confidence ≥ 0.85 → use rule result directly
  │    └─ confidence < 0.85 → llm_router.complete(CallType.ENRICH)
  │         → enrich.py prompt → parse required_skills / difficulty / task_type / domain_tags
  ├─ Update Task fields + status = "open"
  └─ task_logger.created(task)
       └─ TaskCreatedEvent → EventBus → TaskCreatedRedisPublisher
            └─ RedisBus.apublish(TaskCreatedStreamEvent) → XADD stream:task

[Worker]
  TaskStreamSubscriber → TaskBiddingHandler → attempt_reservation → execute_task
```

The `202` is returned immediately. Enrichment and publishing happen asynchronously —
the client never waits for the LLM call.

---

## Task enrichment

Enrichment is the one case where the API process makes an LLM call (documented in
`CLAUDE.md`). It runs in a `BackgroundTask` and is always async relative to the `202`.

**Hybrid approach (Option C from the Notion spec):**

1. `core/intelligence/enrichment.py` — `enrich_rule_based(title, description)` matches the
   lowercased title+description against 4 keyword rules and returns an `EnrichmentResult`
   with a confidence score. Returns `confidence=0.0` when no rule matches.

   | Rule | Keywords (sample) | Confidence |
   |------|-------------------|-----------|
   | `coding` | implement, build, fix, debug, api, endpoint | 0.90 |
   | `research` | research, investigate, analyse, compare | 0.88 |
   | `writing` | write, draft, compose, document, blog | 0.90 |
   | `analysis` | data, metrics, statistics, forecast, model | 0.87 |
   | `general` | *(no match)* | 0.00 |

2. If `confidence ≥ 0.85`, the rule result is used directly — no LLM call.
3. If `confidence < 0.85`, `llm_router.complete(CallType.ENRICH, json_mode=True)` is called
   using the prompt in `core/intelligence/prompts/enrich.py`. The LLM fills
   `required_skills`, `difficulty`, `task_type`, and `domain_tags`.
4. On LLM failure, falls back to the rule result so the task always reaches `"open"`.

---

## Webhook delivery

When a task completes in the worker, Apprise calls the workspace's `result_webhook_url`
with a signed payload.

**Handler → job pattern:**

```
TaskUpdatedEvent (status → "completed")
  └─ WebhookDeliveryHandler (worker/handlers/webhook.py)
       └─ arq_queue.enqueue_job("deliver_webhook", execution_id, workspace_id)

ARQ job: deliver_webhook (worker/jobs/deliver_webhook.py)
  ├─ Load TaskExecution + Workspace from Postgres
  ├─ Create WebhookDelivery row (status="pending", delivery_id="dlv_<hex>")
  ├─ Build JSON payload + HMAC-SHA256 signature
  ├─ POST to result_webhook_url
  │    Header: X-Apprise-Signature: sha256=<hex>
  ├─ Update delivery row (attempt_count, last_http_status, last_error)
  └─ On failure → re-enqueue with delivery_id (same row updated, no duplicate)
       Retry schedule: 30s → 5m → 30m → 2h → failed
```

**Payload:**
```json
{
  "delivery_id": "dlv_<hex>",
  "event": "task.completed",
  "task_id": "<uuid>",
  "workspace_id": "<uuid>",
  "completed_at": "<iso8601>",
  "external_ref": "<string|null>",
  "artefact": { "type": "text", "content": "<artifact_uri>" }
}
```

**Signature verification** (receiving end):
```python
expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
assert request.headers["X-Apprise-Signature"] == f"sha256={expected}"
```

`delivery_id` is a stable dedupe key — if the receiver processes the same `delivery_id`
twice (e.g. network retry after a 200), it should be idempotent.

---

## Redis keys

| Key | TTL | Purpose |
|-----|-----|---------|
| `apikey_valid:{sha256}` | 300s | Cached `ApiKeyPayload` for a validated API key |

All workspace-scoped keys must include `workspace_id` to prevent cross-tenant collision.

---

## Files

| File | Purpose |
|------|---------|
| `api/main.py` | FastAPI app, lifespan, router registration |
| `api/middleware/auth.py` | `AuthMiddleware` — identity resolution only |
| `api/deps.py` | Dep factories: `get_db`, `get_redis`, `get_llm_router`, `require_workspace` |
| `api/routers/workspaces.py` | Workspace CRUD |
| `api/routers/agents.py` | Agent CRUD |
| `api/routers/api_keys.py` | API key create / list / revoke |
| `api/routers/tasks.py` | Task create / get / list + `enrich_and_release` |
| `api/services/auth_service.py` | `validate_api_key`, `revoke_api_key`, `ApiKeyPayload`, `UserPayload` |
| `api/services/workspace_service.py` | Workspace ORM operations |
| `api/services/agent_service.py` | Agent ORM operations |
| `api/services/api_key_service.py` | Key generation, listing, revocation |
| `api/services/task_service.py` | Task creation with idempotency, get, list |
| `api/schemas/` | Pydantic request/response models |
| `api/handlers/task_bridge.py` | `TaskCreatedRedisPublisher` — in-process → Redis Streams bridge |
| `core/intelligence/enrichment.py` | `enrich_rule_based()` — pure, no I/O |
| `worker/handlers/webhook.py` | `WebhookDeliveryHandler` — enqueues on task completion |
| `worker/jobs/deliver_webhook.py` | HTTP delivery, signing, retry |
