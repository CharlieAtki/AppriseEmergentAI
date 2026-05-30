# Worker — Implementation Gaps

Tracks known gaps, design limitations, and deferred improvements in the ARQ worker
(`backend/worker/`). Cross-cutting gaps (audit log, test coverage) are tracked in
[`docs/eventing/event-bus-gaps.md`](../eventing/event-bus-gaps.md).

---

## Open gaps

### ~~1. API key revocation had a 5-minute eventual-consistency window~~

**Gap:** `revoke_api_key()` attempted to delete `apikey_valid:{sha256}` from Redis but
`_sha256_from_hash()` always returned `None` — the raw key is gone at revoke time and
SHA-256 cannot be recovered from bcrypt. The Redis delete was a permanent no-op.

**What was done:**
- `core/models/auth.py` — `key_sha256: Mapped[str | None]` column added (nullable so
  rows created before migration 005 are unaffected).
- `core/migrations/versions/005_add_api_key_sha256.py` — migration adding the column.
- `api/services/api_key_service.py` — `create()` now computes
  `hashlib.sha256(raw_key.encode()).hexdigest()` and stores it as `key_sha256`. The
  SHA-256 is not sensitive (one-way; cannot reconstruct the raw key).
- `api/services/auth_service.py` — `revoke_api_key()` now reads `record.key_sha256`
  and deletes `apikey_valid:{key_sha256}` immediately. `_sha256_from_hash()` removed.
  Keys created before migration 005 (`key_sha256 is None`) still get eventual-consistency
  revocation via the 5-minute cache TTL.

---

### 2. `deliver_webhook` does not commit the `WebhookDelivery` row on first attempt

**Gap:** On the first invocation, `deliver_webhook` creates a `WebhookDelivery` row with
`status=pending` and adds it to the session inside the first `async with get_session()`
block. However, `get_session()` only commits on clean exit — if an exception is raised
between the session closing and the HTTP POST (e.g. during payload construction), the row
is never committed and the delivery has no audit record.

**Impact:** Low probability — the window between session close and HTTP POST is small and
involves only in-memory operations. But a crash here means the delivery silently disappears
with no `WebhookDelivery` row and no retry.

**What is needed:** Commit the row creation as a separate, explicit first step before
building the payload or making the HTTP call. The delivery record should exist regardless
of what happens afterward.

---

### 3. No dead-letter handling for permanently failed webhook deliveries

**Gap:** After 5 total attempts (1 initial + 4 retries at 30s → 5m → 30m → 2h) `deliver_webhook` sets `status="failed"` and logs a
warning. There is no alerting, no customer-facing visibility, and no retry escape hatch.

**What is needed:**
- An admin endpoint or background job that queries `webhook_deliveries WHERE status='failed'`
  and exposes them (or notifies the workspace owner).
- A manual re-trigger path: `POST /workspaces/{id}/webhook-deliveries/{dlv_id}/retry`
  that resets `status`, `attempt_count`, and re-enqueues `deliver_webhook` with the
  existing `delivery_id`.

Defer until customers report the need; the audit trail in `webhook_deliveries` means the
data is there when it is needed.

---

### 4. `decay` cron job may be redundant

**Gap:** `settings.py` runs `decay` as a cron job every 30 seconds. The TODO in that file
questions whether decay should remain on a cron schedule given that `sample_metrics` now
snapshots workspace metrics on its own schedule. If skill decay is already triggered by
task completion events, running it unconditionally every 30 seconds may cause unnecessary
DB writes and interfere with event-driven decay that happens naturally.

**What is needed:** Audit whether `decay` is still needed as a cron or whether it can be
removed in favour of event-driven decay triggered by `TaskUpdatedEvent`. Remove the cron
entry if redundant; document the decision either way.

---

### 5. Worker vendor providers are hard-coded in `context.py`

**Gap:** `WorkerContext.build()` instantiates all four vendor providers (`AnthropicProvider`,
`AzureProvider`, `AWSProvider`, `OllamaProvider`) directly. This is the same coupling
problem as API gap #6 but from the worker side. Notably, the worker registers four vendors
while the API only registers one (Anthropic), which is an inconsistency — if a workspace
routing config references Azure or AWS, the worker can resolve it but the API enrichment
path cannot.

**What is needed:** The same provider self-registration solution that closes API gap #6
also closes this. Defer together. For now, ensure at minimum that the vendor set between
`api/main.py` and `worker/context.py` is kept in sync manually.

---

### ~~6. `AuthMiddleware` used raw `SessionLocal()` instead of `get_session()`~~

**Gap:** Both auth paths in `AuthMiddleware` opened sessions via `SessionLocal()` with
manual commit/rollback/close in a try/except/finally block.

**What was done:** Both paths in `api/api/middleware/auth.py` replaced with
`async with get_session() as session:`. Closed alongside the Clerk JWT fix (H1).

---

### 8. `JobSpan` ContextVar pattern — correctness under ARQ concurrency

**Gap:** `JobSpan` uses a `ContextVar` to make the active span accessible anywhere in the
job call stack without threading it through arguments. This is clean for a single async
task. ARQ runs multiple jobs concurrently as separate asyncio tasks, and `ContextVar` is
correctly scoped per-task — each job's `current_span` is isolated. However, if LangGraph
nodes spawn sub-tasks (e.g. via `asyncio.gather`), those sub-tasks inherit the parent's
context at creation time, which is correct. If they were spawned with `asyncio.create_task`
without explicit context copying, the span would not propagate.

**What is needed:** Audit LangGraph graph execution to confirm no `asyncio.create_task`
call drops the context. If any sub-task spawning does not copy context, pass the context
explicitly: `asyncio.create_task(coro(), context=copy_context())`. If all paths are clean,
document this as validated and close.

---

### 7. Stream event registry (`_REGISTRY`) is static — adding event types requires code changes

**Gap:** `subscriber.py` has a static `_REGISTRY` dict mapping event type strings to
`StreamEvent` subclasses. Adding a new stream event type requires editing this dict.
The in-process `EventBus` uses self-registration (bind at startup); the stream subscriber
does not.

**What is needed:** Either accept the static registry (it's small and the comment already
explains how to extend it) and remove the TODO, or implement self-registration where each
`StreamEvent` subclass declares its own discriminator. The latter is a clean extension of
the existing pattern but adds complexity for marginal gain at current scale. Decision
needed; current state (static dict) is not wrong, just inconsistent with the in-process bus.

---

## Summary

| Gap | Status |
|-----|--------|
| API key revocation eventual consistency (5-min window) | ✅ Closed — `key_sha256` stored at creation; immediate Redis delete on revoke |
| `WebhookDelivery` row not committed before HTTP POST | ❌ Open — low probability, no retry coverage if it hits |
| No dead-letter handling for failed webhook deliveries | ❌ Open — defer until customer need |
| `decay` cron may be redundant | ❌ Open — needs audit against event-driven decay |
| Worker vendor providers hard-coded in `context.py` | ❌ Open — close together with API gap #6; keep in sync manually until then |
| `AuthMiddleware` uses raw `SessionLocal()` | ✅ Closed — both paths now use `async with get_session()` |
| `JobSpan` ContextVar under ARQ concurrency | ❌ Open — audit LangGraph sub-task spawning for context propagation |
| Stream event registry is static | ❌ Open — decide: accept static dict or align with in-process bus self-registration |
