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

### ~~4. `decay` cron job may be redundant~~

**Decision:** Closed. Two separate changes:

**Skill decay** moved to `execute_task` Phase 6 — one flat decay step fires atomically per
task completion for the executing agent. Decay is not quality-weighted: per the Notion spec,
it is entropy/regularization applied uniformly to prevent skill convergence ("skills unused
for a configurable number of ticks lose value gradually"). The quality signal for individual
skills lives in `reflect`, which applies LLM-generated targeted deltas to the skills actually
exercised. Separating these two mechanisms avoids penalising skills unrelated to the task.

**Influence decay** removed from the cron entirely — `AgentCreditHandler` already applies
natural decay via the EMA formula (`new = base + alpha * (quality - base)`): low-quality
completions pull influence down on every task. The cron was double-dipping, misusing
`INFLUENCE_EMA_ALPHA` (an EMA blending rate) as a straight-line decay rate.

`SKILL_DECAY_RATE` semantic change: previously "2% per 30-second tick", now "2% per task
completion". Recalibrate against experimental throughput targets before running emergence
experiments.

---

### ~~10. `RollupSubtaskHandler` reflect enqueue was missing required parameters~~

**Gap:** `RollupSubtaskHandler.handle()` enqueued the `reflect` ARQ job with only
`agent_id`, `task_id`, and `workspace_id`. The `reflect()` job signature requires two
additional parameters — `execution_id: str` and `quality_score: float` — both of which it
uses on every invocation to load the `TaskExecution` row and pass quality context to the
LLM. Without them ARQ raised `TypeError` at deserialisation and silently dropped the job.
The coordinator agent for any decomposed task therefore never received a reflect pass,
meaning no skill deltas were ever applied for the coordination/decomposition path.

**Root cause:** `_evaluate_parent()` did not query for the decompose execution or the
average sibling quality. It returned only `(before_snapshot, parent_task, reflect_agent_id)`.

**What was done:**
- `_evaluate_parent()` return type extended to
  `tuple[..., uuid.UUID | None, float | None]` — adding `(execution_id, avg_quality)`.
- Two additional queries added inside the existing session: one for `func.avg(quality_score)`
  across completed sibling `TaskExecution` rows; one for the parent's decompose
  `TaskExecution.id` (the execution the coordinator ran).
- `handle()` unpacks the new values and passes all five parameters to `enqueue_job`.
  A guard skips the enqueue when either value is `None` (all siblings failed, or no
  decompose execution exists) — preventing a broken job from being queued rather than
  swallowing the failure silently.
- The average sibling quality is the same signal `AgentCreditHandler` uses for
  coordinator influence credit, keeping influence and skill updates consistent.

**File changed:** `worker/worker/handlers/rollup.py` only.

---

### ~~11. Skill updates used flat linear addition — logistic growth not implemented~~

**Gap:** The Notion spec states: *"Skill evolution follows a logistic growth formula. A
skill at 0.3 grows faster than a skill at 0.8, diminishing returns."* The `reflect` job
used `clamp(old + delta, 0, 1)` — a flat linear merge. A +0.3 delta applied the same
absolute gain regardless of current skill level. An agent at 0.9 could reach 1.0 trivially;
an agent at 0.0 could not gain at all below the clamped floor.

**What was done:**
- New pure function `apply_skill_delta(current, delta)` created in
  `core/coordination/skills.py` (alongside `influence.py`, same pattern).
- Formula splits on delta sign:
  - Positive: `new = current + delta * (1 - current)` — growth tapers toward 1.0
  - Negative: `new = current + delta * current` — penalty tapers toward 0.0
- Edge-case safe: at `current=0`, positive delta still produces gain; at `current=1`,
  positive delta produces no overflow; at `current=0`, negative delta produces no
  underflow.
- `reflect.py` import updated; merge dict comprehension now calls `apply_skill_delta`.
  No changes to the LLM prompt — deltas from the model continue to be used as-is.
- `SKILL_DECAY_RATE` delta magnitudes may need recalibration against emergence experiment
  baselines now that gains are logistic rather than linear.

**Files changed:** New `core/coordination/skills.py`; `worker/worker/jobs/reflect.py`.

---

### 13. Embedding model not pre-warmed at startup

**Gap:** The fastembed ONNX model (`qdrant/bge-small-en-v1.5-onnx-q`) is downloaded lazily on the
first call to `get_encoder()` in `core/memory/embeddings.py`. When the worker starts cold and
multiple jobs invoke the `search_episodic_memory` tool concurrently for the first time, they all
race to initialise the encoder simultaneously via `TextEmbedding(settings.memory.embedding_model)`.
The first caller triggers the download from HuggingFace; concurrent callers find partially-written
model files and fail with:

```
onnxruntime.capi.onnxruntime_pybind11_state.NoSuchFile:
  /tmp/fastembed_cache/models--qdrant--bge-small-en-v1.5-onnx-q/snapshots/.../model_optimized.onnx
```

There is no retry path for tool call errors in the graph — the exception propagates out of
`_call_tool`, unwinds through the graph invocation, and lands in the `execute_task` except block.
The task is written to `"failed"` permanently. This only happens once per worker lifetime (after the
model is cached to disk, subsequent restarts find it immediately), but a freshly-provisioned worker
or a cleared `/tmp` will silently fail every task that touches episodic memory until the race window
closes.

**What is needed:** Pre-warm the encoder once in `WorkerContext.build()` before the ARQ worker
begins accepting jobs. A single `get_encoder()` call blocks until the model is fully written to disk;
all subsequent calls hit the in-process cache. No jobs are queued during `startup()`, so there is
no race window.

---

### 14. Unbound tool calls crash the job instead of returning a tool error

**Gap:** When the LLM requests a tool that is not present in the current graph's `tool_map`
(e.g. `execute_code` during a `research`-type task), `_call_tool` raises `KeyError`. This
propagates unhandled through the graph invocation and into the `execute_task` except block,
writing the task to `"failed"` permanently with `{"type": "KeyError", "message": "'execute_code'"}`.

Two things are wrong:

1. **Missing graceful recovery.** The LLM may occasionally hallucinate a tool name, or a task
   type/tool mapping may drift out of sync. In either case the correct response is to return a
   structured tool-error message back to the LLM (e.g. `"tool 'execute_code' is not available"`)
   so the graph can continue and the LLM can recover. A `KeyError` in a tool dispatch should never
   kill the job.

2. **Tool map auditing.** In the observed failure, the `execute_code` tool is likely present in
   the global tool registry but absent from the `research` graph's tool set. The LLM sees the tool
   in its training data and selects it; the graph has never declared it as available. The bound tool
   list passed to `.bind_tools()` at graph compilation is the contract — the LLM should only see
   tools that are in the map. This is already the case if compilation is correct; the gap is that
   there is no assertion or startup check that validates map ↔ bound-tools consistency.

**What is needed:**
- `_call_tool` should catch `KeyError` and return a tool-error dict (following LangChain's tool
  result schema) rather than raising.
- Add a startup assertion in `WorkerContext.build()` that verifies each compiled graph's
  `tool_map` keys match the tools passed to `.bind_tools()`, so map/bound mismatches are caught
  at worker start rather than at runtime.

---

### 15. Runaway decomposition below the difficulty threshold

**Gap:** The evaluate prompt instructs the LLM to "prefer decompose when difficulty ≥ 4". In live
testing with the semiconductor shortage task (parent difficulty 4.5), decomposition cascaded three
levels deep:

- Depth 1 → 6 subtasks (expected — parent difficulty 4.5)
- Depth 2 → 5 sub-subtasks from a difficulty-3.5 subtask (should have been `self_execute`)
- Depth 3 → 3 sub-sub-subtasks from a difficulty-3.0 node (well below threshold)

The LLM consistently ignores the difficulty threshold as a soft guideline and selects `decompose`
for tasks that are complex-sounding but not genuinely difficult enough to warrant delegation. The
only hard stop is the `MAX_DELEGATION_DEPTH = 5` guard in `execute_task.py` — without it,
decomposition would recurse until the rate limit intervened.

**Impact:** Unnecessary decomposition multiplies LLM calls (each depth level triggers one
`EVALUATE` + one `DECOMPOSE` call), burns token budget, fragments tasks into units too small for
meaningful specialisation, and creates large concurrent job spikes that saturate the TPM limit.
Six concurrent subtasks from a single parent is already at the edge of the Tier 1 limit; three
levels of decomposition creates fan-out that a low-tier API key cannot sustain.

**What is needed:**
- Harden the evaluate prompt — replace the soft "prefer decompose when difficulty ≥ 4" guideline
  with an explicit rule: `decompose` is only valid when `difficulty >= 4.0`. Make it a constraint,
  not a preference.
- Consider a code-level guard: if `task.difficulty < settings.DECOMPOSE_DIFFICULTY_THRESHOLD`,
  override any `decompose` decision to `self_execute` before the LLM decompose call fires (same
  pattern as the existing depth guard). This makes the threshold enforceable independently of
  prompt quality.
- Expose `DECOMPOSE_DIFFICULTY_THRESHOLD` in `core/config/` so it can be tuned per experiment
  without code changes.

---

### 12. Influence has no mechanical effect on the evaluate strategy decision

**Gap:** The evaluate prompt (`core/intelligence/prompts/evaluate.py`) sends `agent.influence`
to the LLM as context, but the guidelines contain no rule referencing it. Influence affects
bid scoring (`BID_W_INFLUENCE`) but not the `self_execute / cfp / decompose` strategy choice.

**Design intent:** High-influence agents should lean toward `decompose` (acting as
coordinators) rather than self-executing everything. Low-influence agents should prefer
`self_execute` to build a track record. This is the emergent coordinator pattern the system
is designed to produce — but it cannot emerge without the signal being in the decision rules.

**What is needed:** Add influence-aware guidelines to the evaluate prompt, e.g.:
- `influence > 0.7` → prefer `decompose` for complex tasks (coordinator role)
- `influence < 0.2` → prefer `self_execute` to build influence before delegating
- `cfp` should remain skill-driven, not influence-driven

Thresholds should be tunable (ideally drawn from `settings`) rather than hardcoded in the
prompt string, so emergence experiments can vary them without code changes.

---

### 16. Reflection pipeline — heuristic quality, no failure reflection, episodic/reflect decoupling

**Gap:** Three compounding problems in the post-execution learning layer that block reliable agent emergence. See full analysis: [`reflect-pipeline-gap.md`](./reflect-pipeline-gap.md).

**Summary:**

1. **Quality score is heuristic.** `score_outcome()` measures execution mechanics (artifact presence, step efficiency, tool use), not whether the output answers the task. Agents that produce confident, wrong answers score identically to agents that solve problems correctly. All downstream emergence signals — skill deltas, influence credit, bid scoring — are corrupted by this.

2. **Episodic memory uses the heuristic score and cannot be corrected.** `EpisodicMemoryHandler` fires immediately from the event with the heuristic number. The reflect job runs later with better context but cannot overwrite the Qdrant episode (no point ID tracking). The two systems are temporally decoupled and write different quality values into the same memory tier.

3. **No failure reflection.** Failed tasks produce no episodic record, no skill penalties, no procedural rule. Agents repeat failures without consequence.

**What was done:** Implemented as a unified four-stage pipeline (judge → episodic → skills → rules) under `worker/reflection/`. `EpisodicMemoryHandler` removed. All post-execution writes are owned by `ReflectionManager`. See [`reflect-pipeline-refactor.md`](./reflect-pipeline-refactor.md) for the full design.

- Gap 1 closed — `CallType.JUDGE` (Haiku) overwrites `execution.quality_score` with a semantic assessment of whether the output answers the task.
- Gap 2 closed — episodic write now happens inside `_stage_episodic` after the judge has run, using the semantic score. `EpisodicMemoryHandler` deleted.
- Gap 3 closed — `ReflectJobHandler` fires on `{"completed", "failed"}`; `_stage_episodic` and `_stage_rules` have explicit failure branches.

**Remaining known limitation — episodic duplicate on retry.**

`reflect_completed_at` is stamped after all stages complete. If the process dies between `ReflectionManager.run()` returning and the stamp commit, ARQ retries and all stages re-run. Qdrant has no deduplication on `execution_id`, so `_stage_episodic` writes a second near-identical entry. The values are identical (same execution record, same judge result). No data is corrupted — only duplicated.

Fix if needed: add an `episodic_written_at` column to `TaskExecution`, stamp it at the end of `_stage_episodic`, and check it at stage entry before writing. This gives per-stage idempotency rather than whole-pipeline idempotency.

**Status:** ✅ Closed — pipeline implemented. Episodic retry duplicate is a known, accepted limitation.

---

### 9. `SKILL_DECAY_RATE` is static — no dynamic rate adjustment

**Gap:** `SKILL_DECAY_RATE` (now applied per task completion in Phase 6) is a single static
value. In low-throughput systems (few tasks per hour) this produces negligible decay; in
high-throughput systems (many tasks per minute) it may over-decay before `reflect` has a
chance to reinforce used skills. The rate has no awareness of system load or task frequency.

**What is needed (future):** A dynamic rate adjuster that scales `SKILL_DECAY_RATE` inversely
with recent task throughput — e.g., higher throughput → smaller per-task decay rate so that
the effective decay per unit time stays roughly constant. Could be computed in
`sample_metrics` (which already runs every 15s per workspace) and stored as a
workspace-scoped setting, allowing per-workspace calibration without touching the global
constant.

Defer until emergence experiments produce throughput baseline data to calibrate against.

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
| `decay` cron may be redundant | ✅ Closed — skill decay in Phase 6; influence decay removed (EMA sufficient) |
| Worker vendor providers hard-coded in `context.py` | ❌ Open — close together with API gap #6; keep in sync manually until then |
| `AuthMiddleware` uses raw `SessionLocal()` | ✅ Closed — both paths now use `async with get_session()` |
| `JobSpan` ContextVar under ARQ concurrency | ❌ Open — audit LangGraph sub-task spawning for context propagation |
| Stream event registry is static | ❌ Open — decide: accept static dict or align with in-process bus self-registration |
| `RollupSubtaskHandler` missing reflect params | ✅ Closed — `execution_id` + avg sibling `quality_score` now queried and passed |
| Skill updates used flat linear addition | ✅ Closed — logistic growth implemented in `core/coordination/skills.py` |
| `SKILL_DECAY_RATE` is static | ❌ Open — defer until emergence experiment baselines available |
| Influence not wired into evaluate strategy decision | ❌ Open — high-influence coordinator pattern cannot emerge without it |
| Embedding model not pre-warmed at startup | ❌ Open — concurrent first-use races cause `NoSuchFile`; pre-warm in `WorkerContext.build()` |
| Unbound tool calls crash the job | ❌ Open — `KeyError` in `_call_tool` kills the job; needs graceful tool-error response + startup map validation |
| Runaway decomposition below difficulty threshold | ❌ Open — LLM ignores soft difficulty guideline; needs hard code-level guard + config threshold |
| Reflection pipeline — heuristic quality, no failure reflection, episodic/reflect decoupling | ✅ Closed — four-stage pipeline implemented; episodic retry duplicate is a known accepted limitation |
