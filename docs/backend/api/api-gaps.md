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
  backoff retries (30s → 5m → 30m → 2h), marks `failed` after 5 total attempts (1 initial + 4 retries). `delivery_id` is
  threaded through retries so each attempt updates the same row rather than inserting a duplicate.
- Registered in `worker/startup.py`; `deliver_webhook` added to `WorkerSettings.functions`.
- `httpx>=0.27` added to `worker/pyproject.toml`.

---

### ~~15. Response schema gaps~~

**Gap:** `TaskCreatedResponse` lacked `status` and `workspace_id`; `TaskResponse` was missing
`deadline_at`, `external_ref`, `idempotency_key`.

**What was done:** Both schemas updated; `create_task` returns all three fields.

---

### ~~1. Clerk JWT middleware — `app.state.clerk` not wired~~

**Gap:** The Bearer JWT branch in `AuthMiddleware` was fully implemented but `app.state.clerk`
was never set in the lifespan — any Bearer request hit `AttributeError` and returned 401.
Additionally, the existing `clerk.verify_token(bearer)` call did not exist in the SDK.

**What was done:**
- `core/config/vendors/clerk.py` — `ClerkConfig(env_prefix="CLERK__")` with an empty-string
  default so the worker process doesn't fail on startup when `CLERK__SECRET_KEY` is absent.
- `core/config/__init__.py` — `clerk: ClerkConfig` field added to `Settings`.
- `.env` — `CLERK__SECRET_KEY` placeholder added.
- `api/pyproject.toml` — `clerk-backend-api>=5.0.7` added as a dependency.
- `api/api/main.py` — `Clerk(bearer_auth=...)` instantiated in the lifespan and stored on
  `app.state.clerk`. The SDK fetches Clerk's public JWKS on first call and caches them,
  so subsequent JWT verifications are local crypto with no network round-trip per request.
- `api/api/middleware/auth.py` — Bearer path rewritten to use
  `clerk.authenticate_request_async(request, AuthenticateRequestOptions())` (the correct
  v5 SDK method). Returns a `RequestState`; `req_state.payload` contains `org_id` and `sub`
  which are passed directly to the existing `validate_clerk_token()` DB lookup.
  Both auth paths also migrated from raw `SessionLocal()` to `async with get_session()`.

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

### 7. `CreateTaskRequest` missing `overrides` field

**Gap:** The Notion "Task Ingestion & Result Delivery" spec includes an `overrides` object in
`CreateTaskRequest`:

```json
{
  "overrides": {
    "task_type": "code",
    "required_skills": ["python", "testing"],
    "difficulty": 0.7
  }
}
```

`api/schemas/task.py` has no `overrides` field. Customers with domain knowledge (e.g. CI
systems that know the task is always a coding task) cannot bypass enrichment — every task
goes through rule-based + LLM enrichment regardless.

**What is needed:**

```python
class TaskOverrides(BaseModel):
    task_type: str | None = None
    required_skills: list[str] | None = None
    difficulty: float | None = Field(None, ge=0.0, le=1.0)

class CreateTaskRequest(BaseModel):
    ...
    overrides: TaskOverrides | None = None
```

`enrich_and_release` skips enrichment when all three override fields are set; uses provided
values directly. Partial overrides are merged with enrichment output.

---

### 8. `idempotency_key` should be an HTTP header, not a body field

**Gap:** The Notion spec uses `Idempotency-Key: <uuid>` as an HTTP request header
(consistent with Stripe, OpenAI, and industry convention). The current implementation
accepts `idempotency_key` as a JSON body field inside `CreateTaskRequest`.

**Impact:** Clients following the Notion spec send the header, which is silently ignored.
They get non-idempotent behaviour — a second identical POST creates a second task rather
than returning the first.

**What is needed:** Add `Idempotency-Key` header extraction in the `create_task` router
function (or a FastAPI dependency). If both header and body field are present, prefer the
header. Keep the body field for backwards compatibility during the transition period.

---

### 9. API key prefix format differs from Notion spec

**Gap:** The Notion spec shows API keys with prefix `apk_live_` (e.g. `apk_live_abc123`).
`api_key_service.create()` generates `appr_<first 8 chars of raw_key>` (e.g. `appr_dQ3kzHj9`).

**Impact:** Customer-facing documentation and any client-side key validation that pattern-matches
the prefix will fail.

**What is needed:** Decide on the canonical prefix and apply it consistently. If moving to
`apk_live_` (aligned with Notion), change `api_key_service.create()` and update any prefix
extraction logic in `validate_api_key()` (currently `raw_key[:8]`, would need adjustment if
the prefix is variable-length).

---

### 10. `artifact_uri` column name is misleading

**Gap:** `TaskExecution.artifact_uri` stores the literal text content of the agent's artifact
(a `str | None` from `GraphState.artifact`). The name implies it is a URI or file path. The
webhook payload correctly sends it as `"artefact": {"type": "text", "content": artifact_uri}`
so there is no runtime bug — but the column name will mislead any developer who assumes it
references a file location and tries to fetch/dereference it.

**What is needed:** Rename `artifact_uri → artifact` in `core/models/tasks.py` (requires an
Alembic migration) and update the two references in `deliver_webhook.py`. Low priority — no
customer-visible impact, purely an internal naming issue.

---

### ~~11. No Clerk webhook handler — human JWT auth broken in production~~

**Gap:** `validate_clerk_token` looked up `clerk_org_id` / `clerk_user_id` in the `organisations`
and `users` tables, but nothing ever created those rows. Every Bearer JWT request returned 401
in production because the DB was empty.

**What was done:**
- `api/routers/webhooks/clerk.py` — `POST /webhooks/clerk`, exempt from `AuthMiddleware` via
  `EXEMPT_PREFIXES = {"/webhooks"}`. Svix HMAC signature verified via `_verify_svix` dependency.
- `api/routers/webhooks/__init__.py` — aggregates webhook routers; registered at `/webhooks` in `main.py`.
- `api/services/clerk_webhook_service.py` — `ClerkWebhookService.handle()` dispatches on event type.
  Handles: `organization.created/deleted`, `user.created/deleted`, `organizationMembership.created/deleted`.
  Unknown event types silently return 200 (prevents Svix retry loops).
- `core/repositories/org_repository.py` — `upsert()`, `delete_by_external_id()`, `upsert_member()`,
  `delete_member()` added. All writes use PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` for idempotency.
- `core/repositories/user_repository.py` — `upsert()`, `delete_by_external_id()` added.
- `core/config/vendors/clerk.py` — `webhook_secret: SecretStr` added (`CLERK__WEBHOOK_SECRET`).
- `api/pyproject.toml` — `svix>=1.96.1` added.
- `docker-compose.yml` — `CLERK__WEBHOOK_SECRET` passed through to api container.
- See `docs/backend/api/clerk-identity-sync.md` for full design rationale.

---

### 12. API key scope system has no role abstraction

**Gap:** `require_workspace()` in `deps.py` checks for granular scope strings like `"tasks:write"`.
There is no role layer — no `admin` / `operator` / `readonly` role that expands to a set of
scopes at key creation time. Dev keys use `scopes=None` (unrestricted) as a workaround.

**Impact:** The key creation endpoint (`POST /workspaces/{id}/api-keys`) accepts arbitrary
scope strings. There is no validation, no canonical list, and no documentation of what scopes
exist. Callers must know the exact internal strings.

**What is needed:** A role enum (`admin`, `operator`, `readonly`) that maps to a fixed scope
set at key creation. The underlying string check in `deps.py` stays untouched — roles just
pre-populate `scopes` with the right list.

---

### 13. Enrichment classification accuracy

**Gap:** The rule-based classifier in `core/intelligence/enrichment.py` uses greedy first-match
keyword rules. Rules match on short, common words (e.g. `"api"` in the coding rule) that appear
frequently in non-coding tasks. A research task titled "Design a microservices architecture" with
"API contracts" in the description will be classified as `coding` with confidence 0.9 — and because
confidence exceeds the 0.85 threshold, the LLM escalation never fires.

The result: tasks are silently mis-classified, no agents bid on them (skill mismatch), and they
expire. The bug is invisible — no error is logged, the task reaches `"open"` status, and the worker
simply finds no qualifying agents.

**What is needed:** Solution not yet decided. The problem is well-understood; the right fix
requires more thought.

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
| Clerk JWT middleware for human users | ✅ Closed |
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
| `overrides` field missing from `CreateTaskRequest` | ✅ Closed — `TaskOverrides` + unified `enrich()` in core |
| `idempotency_key` is a body field, not HTTP header | ✅ Closed — `Idempotency-Key` header wins; body field kept |
| API key prefix format (`appr_` vs `apk_live_`) | ✅ Closed — full key is now `apk_live_{token}` |
| `artifact_uri` column name misleading | ✅ Closed — renamed to `artifact`, migration 006 |
| No Clerk webhook handler | ❌ Open — human JWT auth returns 401 in production; seed workaround for dev |
| API key scope system has no role abstraction | ❌ Open — no Admin/Operator/Readonly roles; callers must know internal scope strings |
| Enrichment classification accuracy | ❌ Open — coarse keyword rules cause silent mis-classification; LLM fallback never fires for high-confidence wrong matches |
