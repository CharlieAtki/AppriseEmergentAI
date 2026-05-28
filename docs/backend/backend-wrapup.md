# Backend — State of Play

This document consolidates everything outstanding across the backend. It is written against
the current codebase state after the latest pull. Gap docs for individual subsystems remain
the canonical source; this is the unified view.

---

## What is done

The core platform is built end-to-end. A task submitted via the API reaches an agent, is
executed (including multi-level decomposition and CFP delegation), and delivers a signed
webhook on completion. The coordination layer is correct: influence credit reaches the right
agents via `AgentCreditHandler`, the CFP path has a real subscriber, and the rollup handler
closes parent tasks when all subtasks terminate.

At a glance:

| Area | State |
|------|-------|
| API — auth, workspace, task, agent, api-key routers | ✅ Done |
| Task enrichment (rule-based + LLM hybrid) | ✅ Done |
| Redis Streams bridge (API → Worker) | ✅ Done |
| Worker bidding (`TaskBiddingHandler`, `compute_bid_score`) | ✅ Done |
| Task execution (`execute_task` job, LangGraph graph) | ✅ Done |
| ContractNet CFP path (subscriber, `CfpHandler`, influence credit) | ✅ Done |
| Subtask decomposition + rollup (`RollupSubtaskHandler`) | ✅ Done |
| Coordinator credit — all three execution paths | ✅ Done |
| Webhook delivery with HMAC signing and exponential backoff | ✅ Done |
| Memory — episodic, procedural, social writes | ✅ Done |
| Nightly curation cron (`curate_memory`) | ✅ Done |
| Metrics sampling cron (`sample_metrics`) | ✅ Done |
| Task sweeper cron (`sweep_tasks`) — stuck-open, deadline violations, stale reservations | ✅ Done |

---

## Outstanding gaps

The gaps below are the complete open set drawn from every gap doc. They are grouped by
where the work lands, ordered roughly by impact.

---

### API

#### 1. Clerk JWT middleware is wired but not activated

`AuthMiddleware` has a full `validate_clerk_token` implementation — it does the DB lookup
and maps Clerk string IDs (`clerk_user_id`, `clerk_org_id`) to internal UUIDs. The Bearer
branch runs. But `app.state.clerk` is never assigned in the FastAPI lifespan, so every
Bearer request hits `AttributeError` and returns 401. Machine clients using `X-API-Key`
are unaffected.

**What is needed:**

```python
# api/api/main.py — inside the lifespan async with block
from clerk_backend_api import Clerk
app.state.clerk = Clerk(secret_key=settings.clerk_secret_key)
```

Add `CLERK_SECRET_KEY` to both `config.py` (as a `str` field with no default) and `.env`.
That is the entire change — the rest of the auth path already works.

---

#### 2. No metrics endpoints

`WorkspaceMetricsSnapshot` and `EmergenceEvent` rows are written by the `sample_metrics`
cron but there is no HTTP surface to read them. Customers and internal dashboards have no
way to query workspace health.

**What is needed:**

```
GET /workspaces/{id}/metrics    → latest WorkspaceMetricsSnapshot row
GET /workspaces/{id}/emergence  → recent EmergenceEvent rows (paginated)
```

Follow the pattern of `workspaces.py`: thin router, service function, Pydantic response
schema. No business logic in the router.

---

#### 3. No batch task endpoint

The spec requires bulk ingestion of up to 100 tasks in a single request. Submitting 100
individual POSTs is not a viable integration pattern for high-volume clients.

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

Validate all tasks, collect per-index errors rather than fail-fast, write all valid tasks
in a single `flush()`, commit once, schedule `enrich_and_release` for each. Route:
`POST /workspaces/{id}/tasks/batch`.

---

#### 4. No bulk polling endpoint

Clients that cannot expose a public webhook must poll for results. Per-task polling does
not scale. The spec defines:

```
GET /workspaces/{id}/tasks?status=completed&since=<ISO-timestamp>
```

This is a keyset-paginated query on `(workspace_id, status, updated_at)`. An index on
those three columns in that order is required before shipping — without it, the query
table-scans on every call.

---

#### 5. `CreateTaskRequest` missing `overrides` field

Customers with domain knowledge (a CI pipeline that always submits coding tasks) cannot
bypass enrichment — every task goes through rule-based and potentially LLM enrichment
regardless. The spec includes an `overrides` object for exactly this case.

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

`enrich_and_release` skips enrichment when all three fields are set and uses the provided
values directly. Partial overrides are merged with enrichment output.

---

#### 6. `idempotency_key` should be an HTTP header, not a body field

Industry convention (Stripe, OpenAI, the Notion spec) puts idempotency keys in an
`Idempotency-Key` request header, not the JSON body. The current implementation accepts
`idempotency_key` as a body field. Clients following the spec send the header, which is
silently ignored — a second identical POST creates a second task rather than returning
the first.

**What is needed:** Extract `Idempotency-Key` from the request headers in `create_task`
(or a FastAPI dependency). If both header and body field are present, prefer the header.
Keep the body field for backwards compatibility during the transition.

---

#### 7. API key prefix format mismatch

The spec shows `apk_live_<token>`. The implementation generates `appr_<first 8 chars>`.
This is customer-facing — any client-side prefix validation or key display will differ
from the documentation.

**What is needed:** Decide on the canonical prefix and apply it consistently. Changing
to `apk_live_` requires updating `api_key_service.create()` and the prefix extraction
logic in `validate_api_key()` (currently takes `raw_key[:8]`, needs adjustment if the
prefix has variable length).

---

#### 8. `artifact_uri` column name is misleading

`TaskExecution.artifact_uri` stores the literal text content of the agent's artifact — a
`str | None` from `GraphState.artifact`. The name implies a file path or URI. There is no
runtime bug (the webhook payload wraps it correctly as `{"type": "text", "content": ...}`)
but any developer reading the column name will assume it can be dereferenced.

**What is needed:** Rename `artifact_uri → artifact` in `core/models/tasks.py`, add an
Alembic migration, and update the two references in `deliver_webhook.py`. Low priority —
purely an internal naming issue with no customer-visible impact.

---

#### 9. Vendor provider wiring is hard-coded in `main.py`

`AnthropicProvider` is instantiated directly in the FastAPI lifespan. Adding a second
vendor requires editing `main.py`. Model registration is already self-registering (importing
a vendor package is the act of registering it) but provider instantiation is not.

**What is needed:** Each vendor `__init__.py` registers a provider factory alongside its
models. The lifespan calls a single `build_vendor_providers(config)` helper and passes the
result to `LLMRouter`. No vendor names appear in `main.py`.

**When to do it:** Only when a second vendor is added. Do not abstract prematurely.
The same change closes worker gap #5 — do both together.

---

#### 10. No WebSocket live dashboard

The spec defines `GET /workspaces/{id}/stream` (WebSocket): on connect, send the current
agent and metrics snapshot; then forward `workspace:{id}:events` Redis Pub/Sub messages
to the browser in real time. Disconnect must clean up the subscription — leaked
subscriptions compound linearly with workspace count.

This is a larger piece of work. Defer until customer demand justifies it.

---

### Worker

#### 1. API key revocation has a 5-minute window

`revoke_api_key()` sets `revoked=True` in Postgres and attempts to delete the Redis cache
entry (`apikey_valid:{sha256}`). But the cache key is `SHA-256(raw_key)` and at revoke
time only the bcrypt hash is available — the raw key is gone. `_sha256_from_hash` returns
`None`, so the Redis delete is a no-op. A revoked key continues to authenticate for up to
5 minutes.

This is acceptable for most cases but fails an immediate-revocation requirement (leaked
key, employee offboarding).

**Fix (Option A — correct):** Add a `key_sha256 TEXT NOT NULL` column to `api_keys` at
creation time. `api_key_service.create()` computes `SHA-256(raw_key)` and stores it.
`revoke_api_key()` reads `key_sha256` and deletes `apikey_valid:{key_sha256}` immediately.
This is a one-column Alembic migration and a two-line change. The SHA-256 is not sensitive
— it cannot be reversed to the raw key.

**Fix (Option B — partial):** Reduce the cache TTL from 300s to 60s. Simpler but still
leaves a window and increases DB load on every auth check.

Option A is the right fix.

---

#### 2. `WebhookDelivery` row not committed before the HTTP POST

On the first invocation of `deliver_webhook`, the `WebhookDelivery` row is created with
`status=pending` inside an `async with get_session()` block. If any exception is raised
between the session closing and the HTTP POST (during payload construction), `get_session()`
never commits. The row is gone — no audit record and no retry.

The probability is low (the window involves only in-memory operations) but a crash here
leaves the delivery silently lost.

**Fix:** Commit the row creation as an explicit first step before building the payload or
making the HTTP call. The delivery record should exist regardless of what happens afterward.

---

#### 3. No dead-letter handling for permanently failed webhook deliveries

After 5 total attempts (1 initial + 4 retries at 30s → 5m → 30m → 2h), `deliver_webhook`
sets `status="failed"` and logs a warning. There is no alerting, no customer-facing
visibility, and no manual re-trigger path.

**Fix directions:**
- An admin endpoint or background job that queries `webhook_deliveries WHERE status='failed'`.
- A manual retry route: `POST /workspaces/{id}/webhook-deliveries/{dlv_id}/retry` that
  resets `status`, resets `attempt_count`, and re-enqueues `deliver_webhook` with the
  existing `delivery_id`.

The `webhook_deliveries` table already has the data. Defer until a customer reports the
need.

---

#### 4. `decay` cron may be redundant

`settings.py` runs `decay` as a cron job every 30 seconds alongside `sample_metrics` (every
15s), `curate_memory` (nightly), and the new `sweep_tasks` (every 5 minutes). The TODO
questions whether skill decay still needs a cron at all — if `InfluenceUpdateHandler` /
`AgentCreditHandler` already applies decay as a side effect of task completion events, the
unconditional 30-second invocations cause unnecessary DB writes with no additional effect.

**What is needed:** Audit whether event-driven decay via `TaskUpdatedEvent` fully covers
what the cron does. Remove the cron entry if redundant and document the decision. If it is
still needed, remove the TODO comment so the question is settled.

---

#### 5. Worker vendor providers are hard-coded in `context.py`

`WorkerContext.build()` instantiates all four vendor providers (`AnthropicProvider`,
`AzureProvider`, `AWSProvider`, `OllamaProvider`) directly. This is the same coupling
problem as API gap #9.

Note the inconsistency: the worker registers four vendors; the API only registers one
(Anthropic). A workspace routing config that references Azure or AWS will resolve
correctly in the worker but fail silently during API-side enrichment.

**Fix:** The self-registration solution for API gap #9 also closes this. Do them together.
Until then, manually keep the vendor set in `api/main.py` and `worker/context.py` in sync.

---

#### 6. `AuthMiddleware` uses raw `SessionLocal()` instead of `get_session()`

Both auth paths in `AuthMiddleware` open a session via `SessionLocal()` with manual
`commit / rollback / close` in a try/except/finally block. Every other session usage in
the codebase uses `async with get_session()` which handles this automatically.

Middleware cannot use `Depends()`, but it can use the async context manager directly:

```python
from core.database import get_session
async with get_session() as session:
    payload = await validate_api_key(api_key, request.app.state.redis, session)
```

This removes the manual error handling and aligns with the rest of the codebase.

---

#### 7. `JobSpan` ContextVar correctness under ARQ concurrency

`JobSpan` uses a `ContextVar` to make the active span accessible anywhere in a job's
call stack without threading it through arguments. `ContextVar` is correctly scoped
per-asyncio-task so concurrent ARQ jobs are isolated from each other.

The risk is in LangGraph nodes: if the graph spawns sub-tasks with `asyncio.create_task`
without explicitly copying the context, the span does not propagate to those sub-tasks.

**What is needed:** Audit LangGraph graph execution in `core/agents/graphs/` to confirm
no `asyncio.create_task` call drops the context. If any do, pass context explicitly:
`asyncio.create_task(coro(), context=copy_context())`. If all paths are clean, remove
the open marker in the gap doc.

---

#### 8. Stream event registry is static

`subscriber.py` has a static `_REGISTRY: dict[str, type[StreamEvent]]` mapping event
type strings to their classes. Adding a new stream event type requires editing this dict
manually. The in-process `EventBus` uses self-registration (bind at startup); the Redis
stream subscriber does not — it is the only inconsistency in the event model.

**Decision needed:** Accept the static registry (it is small, the extension comment is
clear, rename the TODO to a note) — or implement self-registration where each `StreamEvent`
subclass declares its own discriminator and registers automatically on import. The latter
aligns the two buses but adds complexity for marginal gain at current scale.

---

### Event bus

#### 1. No audit log handler

The `EventBus` is wired in both processes, handlers for rollup, bidding, social memory,
and CFP are all registered, but there is no handler that writes an audit record for every
task and agent lifecycle event. This is the most immediately useful addition to the event
layer.

The handler itself is straightforward — it follows the same pattern as
`RollupSubtaskHandler`:

```python
class TaskAuditLogHandler(EventHandler[TaskCreatedEvent]):
    async def handle(self, event: TaskCreatedEvent) -> None:
        async with get_session() as session:
            session.add(AuditLogEntry(
                workspace_id=event.workspace_id,
                entity_type="task",
                entity_id=event.state.id,
                action="created",
                snapshot=dataclasses.asdict(event.state),
            ))
```

**Blocked on:** The `audit_log` table and `AuditLogEntry` ORM model do not exist. The
handler cannot be written until the schema migration is in place.

Registration goes in both `worker/startup.py` (the worker creates and updates tasks) and
`api/api/main.py` (the API creates and deletes entities via its own `EventBus` instance).

---

#### 2. No tests

Nothing in the event layer, coordination layer, or worker handlers is tested. This is
the largest quality gap in the codebase. The `InMemoryBus` already exists as the test
double for `RedisBus` — the infrastructure to write good tests is already there.

Priority order:

| Test file | What it covers |
|-----------|----------------|
| `test_bidding_handler.py` | Agent scoring, threshold filtering, reservation, `execute_task` enqueue, no-agents path |
| `test_rollup_handler.py` | Sibling query, all-terminal trigger, partial failure, concurrent race guard, reflect job enqueue |
| `test_event_bus.py` | `bind`, MRO routing, fire-and-forget, `drain_pending`, subscriber lifecycle |
| `test_activity_loggers.py` | `TaskActivityLogger` publishes correct events; `AsyncMock` as publish callable |
| `test_snapshots.py` | `from_domain` for flat fields, nested snapshots, nullable fields, tuple collections |
| `test_stream_subscriber.py` | `_parse_stream_event` for each type, unknown type returns `None`, start/stop lifecycle |
| `test_handlers.py` | `Retry` backoff, `Filtering` predicate, `Timeout` cancellation, `SyncToAsync` dispatch |
| `test_social_memory_handler.py` | Peer query, fan-out, single peer failure does not block others |
| `test_task_context.py` | `TaskContext.from_task()`, `MAX_DELEGATION_DEPTH`, depth guard in `execute_task` |

`test_bidding_handler.py` and `test_rollup_handler.py` are highest priority — they cover
the most complex stateful logic with the most edge cases.

---

### Memory (all deferred to Phase 2+)

These are known, documented, and intentionally deferred. They do not block Phase 1.

#### 1. Task `description` not in episodic text

`TaskSnapshot` does not carry `description`. Episodic writes use only `title`, `task_type`,
and `domain_tags`. Description is the richest natural-language signal for semantic
retrieval. **Fix:** Add `description: str | None` as a synthetic field to `TaskSnapshot`
and pass it through `task_logger.updated()` in `execute_task`.

#### 2. No episodic write on task failure

`EpisodicMemoryHandler` only fires on `status == "completed"`. Failed tasks produce no
episodic record, but failure is informative signal for future bid scoring. **Fix:** Lower
the guard to `status in {"completed", "failed"}` with a conditional quality string.
Requires verifying that failed-task snapshots carry sufficient metadata.

#### 3. `curate_memory` prompt quality and audit trail

The nightly curation LLM call reviews all procedural rules in a single pass — risky for
agents with 50+ rules. Archival is irreversible and leaves no audit trail. **Fix:** batch
by domain, write a `CurationAuditEntry` to Postgres for each archived rule, and trigger
on collection size rather than a calendar schedule.

#### 4. Reflect job does not write `key_learning` to episodic

`reflect.py` writes to procedural memory only. The Hermes analysis recommends the reflect
job also extract a `key_learning` (one-sentence agent-perspective insight) and write it
to episodic with `source: "reflect"`. **Fix:** Add `key_learning: str` to `ReflectResponse`,
update the prompt, and call `wctx.memory.store_episode()` in `reflect.py`.

#### 5. `tool_trace` not available for episodic enrichment

The episodic text could include a summary of tools used (`"Tools: web_search, execute_code"`),
giving retrieval a stronger signal for tool-use similarity. `tool_trace` is on
`TaskExecution` but not on `TaskSnapshot`. **Fix (preferred):** Add `tool_names:
tuple[str, ...]  | None` as a synthetic snapshot field, derived from `execution.tool_trace`
in `execute_task`.

#### 6. Episodic tier has no complexity gate

Every self-execute completion writes an episodic entry regardless of difficulty. Over many
ticks, low-signal trivial completions dominate the top-k retrieval results for complex
tasks. **Fix:** Mirror the gate in `reflect.py` — only write for `difficulty >= 2` or
`step_count > 1`. Requires `step_count` from `tool_trace` (see gap above).

#### 7. Social memory fan-out at scale

With N agents, each task completion triggers N−1 `store_social()` calls, each an async
Qdrant upsert with an embedding call. At 50 agents this is 49 concurrent upserts per
completion. **Fix:** batch the upserts into a single `client.upsert()` call; consider
sampling agents whose social observations are recent. Non-issue at Phase 1 scale.

---

## Summary table

| Gap | Area | Priority |
|-----|------|----------|
| Clerk JWT — `app.state.clerk` not set | API | High — human users cannot log in |
| No metrics endpoints | API | Medium |
| No batch task endpoint | API | Medium — blocks high-volume integrations |
| No bulk polling endpoint | API | Medium — blocks webhook-less integrations |
| `overrides` field missing | API | Medium |
| `idempotency_key` should be HTTP header | API | Medium — spec misalignment |
| API key prefix format (`appr_` vs `apk_live_`) | API | Low — naming decision |
| `artifact_uri` column name | API | Low — internal rename |
| Vendor provider wiring hard-coded | API + Worker | Low — defer until second vendor |
| No WebSocket dashboard | API | Low — defer until customer demand |
| API key revocation 5-min window | Worker | High if immediate revocation is required |
| `WebhookDelivery` row not committed first | Worker | Low — low probability window |
| No dead-letter handling | Worker | Low — defer until customer need |
| `decay` cron audit | Worker | Low — may be removable |
| `AuthMiddleware` raw `SessionLocal()` | Worker | Low — cleanup |
| `JobSpan` ContextVar audit | Worker | Low — needs code audit |
| Stream event registry static | Worker | Low — consistency decision |
| No audit log handler (needs table first) | Event bus | Medium |
| No tests | Event bus | High — largest quality gap |
| Memory gaps 1–7 | Memory | Deferred — Phase 2+ |