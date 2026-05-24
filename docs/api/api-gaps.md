# API — Implementation Gaps

The API structure (`main.py`, `deps.py`, routers, middleware, service layer, event bridge)
is scaffolded. The following tracks what has been closed and what remains, in the same
format as `coordination-gaps.md` and `event-bus-gaps.md`.

---

## Closed gaps

### ~~1. Root tasks invisible to worker bidding~~

**Gap:** The API had no `POST /workspaces/{id}/tasks` route, and no mechanism to publish
`task.created` to Redis Streams.

**What was done:**
- `api/handlers/task_bridge.py` — `TaskCreatedRedisPublisher` registered on the in-process `EventBus`.
- `api/routers/tasks.py` — POST / GET / list endpoints.
- `api/services/task_service.py` — `TaskService` encapsulates all ORM logic.
- `api/schemas/task.py` — `CreateTaskRequest`, `TaskCreatedResponse`, `TaskResponse`.

---

### ~~2. API-key validation is a stub~~

**Gap:** `AuthMiddleware` accepted any non-empty `X-API-Key` header with a hardcoded org_id.

**What was done:**
- `api/services/auth_service.py` — `validate_api_key(raw_key, redis, session)`:
  SHA-256 of raw key → Redis cache lookup (`apikey_valid:{hash}`, 5-min TTL) → on miss,
  narrow by `key_prefix`, loop with `bcrypt.verify()` against candidates, check expiry, cache result.
- `api/middleware/auth.py` — rewritten as `AuthMiddleware`: dispatches on header type
  (`X-API-Key` → API key path; `Authorization: Bearer` → Clerk JWT path stub).
- Revoke path: `revoke_api_key()` sets `revoked=True` and deletes the Redis cache entry immediately.

---

### ~~3. `require_workspace` has no DB lookup or permission check~~

**Gap:** The dep returned a hardcoded dict; no ownership, active-status, or scope checks.

**What was done:**
- `api/deps.py` — `require_workspace(permission)` factory loads the `Workspace` ORM model,
  verifies `ws.organisation_id == auth.org_id`, checks `ws.status == "active"`, checks
  `tasks:write` scope on write routes. Returns the ORM model — routes read `workspace.id`
  and `workspace.organisation_id` directly.

---

### ~~4. Double session bug in `create_task`~~

**Gap:** Route injected a second `session` dep and committed on the wrong session.

**What was done:** Removed the explicit `session` dep; added `TaskService.commit()` called
after `service.create()` so the row is durable before the background task runs.

---

### ~~5. `enrich_and_release` opens raw `SessionLocal()`~~

**Gap:** Background task leaked sessions on exceptions.

**What was done:** Replaced with `async with get_session() as session:` which commits on
success, rolls back on any exception, and always closes.

---

### ~~6. No API key generation / revocation endpoints~~

**Gap:** No way to create, list, or revoke API keys via HTTP.

**What was done:**
- `api/schemas/api_key.py` — `CreateApiKeyRequest`, `ApiKeyCreatedResponse` (raw key shown once),
  `ApiKeyResponse`.
- `api/services/api_key_service.py` — `create()` generates `secrets.token_urlsafe(32)`,
  bcrypt-hashes it, stores `key_prefix = f"appr_{raw_key[:8]}"`. `revoke()` delegates to
  `auth_service.revoke_api_key()` which deletes the Redis cache entry.
- `api/routers/api_keys.py` — `POST/GET /workspaces/{id}/api-keys`,
  `DELETE /workspaces/{id}/api-keys/{kid}`.

---

### ~~7. No workspaces router~~

**Gap:** `workspace_id` is a non-nullable FK on every operational model; no way to create workspaces.

**What was done:**
- `api/schemas/workspace.py`, `api/services/workspace_service.py`, `api/routers/workspaces.py`.
- Routes: `POST/GET /workspaces`, `GET/PATCH/DELETE /workspaces/{id}`.
- `PATCH` is how customers register `result_webhook_url` and `webhook_secret`.

---

### ~~8. No agents router~~

**Gap:** No HTTP surface to create agents or inspect the pool.

**What was done:**
- `api/schemas/agent.py`, `api/services/agent_service.py`, `api/routers/agents.py`.
- Routes: `POST/GET /workspaces/{id}/agents`, `GET/PATCH /workspaces/{id}/agents/{aid}`.

---

### ~~10. Task enrichment is a stub~~

**Gap:** `enrich_and_release()` transitioned `"enriching"` → `"open"` with no enrichment;
`required_skills` was always `None`.

**What was done:**
- `core/intelligence/enrichment.py` — pure `enrich_rule_based(title, description)` function.
  Matches against 4 keyword rules (coding / research / writing / analysis); returns a fallback
  with `confidence=0.0` when no rule matches.
- `enrich_and_release` in `api/routers/tasks.py` uses the hybrid approach: rule-based first;
  if `confidence < 0.85`, escalates to `llm_router.complete(CallType.ENRICH, ...)` using the
  existing `enrich.py` prompt. Falls back to rule result if the LLM call fails.
- `LLMRouter` added to the FastAPI lifespan (`app.state.llm_router`), limited to 2 concurrent
  calls (API enrichment only). `get_llm_router` dep added to `api/deps.py`.

---

### ~~12. No webhook delivery on task completion~~

**Gap:** `WebhookDelivery` table existed; nothing wrote to it.

**What was done:**
- `worker/handlers/webhook.py` — `WebhookDeliveryHandler(EventHandler[TaskUpdatedEvent])`:
  fires when `status` transitions to `"completed"` and `execution_id` is set; enqueues
  `deliver_webhook` ARQ job. No HTTP, no payload construction — handler only enqueues.
- `worker/jobs/deliver_webhook.py` — ARQ job: loads execution + workspace inside a session
  (captures `target_url`, `webhook_secret`, `artifact_uri` as locals before the session closes),
  creates `WebhookDelivery` row, POST with `X-Apprise-Signature: sha256=<hmac>`, exponential
  backoff retries (30s → 5m → 30m → 2h), marks `failed` after 4 attempts. `delivery_id` is
  threaded through retries so each attempt updates the same row rather than inserting a duplicate.
- Registered in `worker/startup.py`; `deliver_webhook` added to `WorkerSettings.functions`.
- `httpx>=0.27` added to `worker/pyproject.toml`.

---

### ~~15. Response schema gaps~~

**Gap:** `TaskCreatedResponse` lacked `status` and `workspace_id`; `TaskResponse` was missing
`deadline_at`, `external_ref`, `idempotency_key`.

**What was done:** Both schemas updated; `create_task` returns all three fields.

---

### ~~16. Idempotency key not enforced~~

**Gap:** Duplicate submission with the same `idempotency_key` crashed with a raw 500.

**What was done:** `TaskService.create()` wraps `flush()` in an `IntegrityError` catch;
rolls back, queries by `(workspace_id, idempotency_key)`, returns the existing task.

---

### ~~17. Insufficient task schema validation~~

**Gap:** No semantic validation on `description`, `deadline_at`, or `priority`.

**What was done:** `CreateTaskRequest` gains three `@field_validator`s — description
minimum 10 chars, `deadline_at` must be in the future, `priority` must be one of
`low / normal / high / critical`.

---

## Open gaps

### 1. Clerk JWT middleware — `app.state.clerk` not wired

**Gap:** The Bearer JWT branch in `AuthMiddleware` is implemented (`validate_clerk_token`
does the DB lookup and maps Clerk string IDs → internal UUIDs) but `app.state.clerk` is
never set in the lifespan. Any Bearer request hits `AttributeError` and returns 401.

**What is needed:**
1. Instantiate `Clerk(secret_key=settings.clerk_secret_key)` in the FastAPI lifespan,
   store on `app.state.clerk`.
2. Add `CLERK_SECRET_KEY` to `.env` and `config.py`.

---

### 6. Vendor provider wiring is hard-coded in `main.py`

**Gap:** `AnthropicProvider` is instantiated directly in the lifespan. Adding a second
vendor requires editing `main.py`. Model registration is already self-registering (import =
register via `__init__.py` side-effect); provider instantiation is not.

**What is needed:** Each vendor `__init__.py` also registers a provider factory alongside
its models. The lifespan calls a single `build_vendor_providers(config)` helper and passes
the result to `LLMRouter` — no vendor names appear in `main.py`. Only worth doing when a
second vendor is added; don't abstract prematurely.

---

### 2. No `metrics.py` router

**Gap:** `WorkspaceMetricsSnapshot` and `EmergenceEvent` are written by cron jobs but there
is no endpoint to read them.

**What is needed:**
```
GET /workspaces/{id}/metrics    → latest WorkspaceMetricsSnapshot
GET /workspaces/{id}/emergence  → recent EmergenceEvents
```

---

### 3. No `POST /workspaces/{id}/tasks/batch` endpoint

**Gap:** The Notion "Task Ingestion & Result Delivery" doc specifies bulk task ingestion
(up to 100 tasks per request).

**What is needed:**
```python
class BatchCreateTaskRequest(BaseModel):
    tasks: list[CreateTaskRequest] = Field(..., max_length=100)

class BatchCreatedResponse(BaseModel):
    accepted: int
    rejected: int
    tasks: list[TaskCreatedResponse]
    errors: list[dict]   # {"index": int, "reason": str}
```
Collect validation errors rather than fail-fast, write all valid tasks in a single flush,
commit once, schedule `enrich_and_release` for each.

---

### 4. No bulk polling endpoint

**Gap:** Customers who cannot expose a webhook must poll per `task_id`. Notion specifies:
```
GET /workspaces/{id}/tasks?status=completed&since=<ISO-timestamp>
```

---

### 5. No WebSocket live dashboard

**Gap:** `GET /workspaces/{id}/stream` (WebSocket) is specified in the Notion doc.
On connect: send current agent + metrics snapshot. Then forward `workspace:{id}:events`
Redis Pub/Sub messages to the browser in real time. Must clean up the subscription on
disconnect (leaked subscriptions compound with workspace count).

---

## Summary

| Gap | Status |
|-----|--------|
| Root tasks invisible to worker bidding | ✅ Closed |
| API-key validation stub | ✅ Closed |
| Clerk JWT middleware for human users | ❌ Open |
| `require_workspace` stub | ✅ Closed |
| Double session bug in `create_task` | ✅ Closed |
| `enrich_and_release` raw `SessionLocal()` | ✅ Closed |
| No API key endpoints | ✅ Closed |
| No workspaces router | ✅ Closed |
| No agents router | ✅ Closed |
| No metrics router | ❌ Open |
| Vendor provider wiring hard-coded | ❌ Open (defer until second vendor) |
| Task enrichment stub | ✅ Closed |
| No webhook delivery | ✅ Closed |
| Batch task ingestion | ❌ Open |
| Bulk polling endpoint | ❌ Open |
| WebSocket live dashboard | ❌ Open |
| Response schema gaps | ✅ Closed |
| Idempotency key not enforced | ✅ Closed |
| Insufficient task schema validation | ✅ Closed |