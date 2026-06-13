# Memory Layer — Gaps & Future Work

Tracks known gaps, design limitations, and deferred improvements in the three-tier memory system (episodic, procedural, social). Ordered roughly by impact.

Cross-cutting gaps (audit log, API→Redis bridge, test coverage) are tracked in [`docs/eventing/event-bus-gaps.md`](../eventing/event-bus-gaps.md).

---

## 1. Task `description` not available in `TaskSnapshot`

**What:** `Task.description` is not included in `TaskSnapshot`. The episodic write text in `_build_episodic_entry` already includes `description` (read directly from the ORM), so the immediate retrieval gap is closed. The remaining issue is that event handlers receiving `TaskUpdatedEvent` do not have access to `description` from the snapshot alone.

**Why it matters:** Handlers that need description must re-query the DB, adding a round-trip inside what should be a fire-and-forget handler.

**Fix:** Add `description: str | None` to `TaskSnapshot` as a synthetic field. Pass it from `execute_task` via `task_logger.updated()`. The episodic text already uses description — this change is about making it available to downstream event handlers without a DB read.

**Deferred because:** Phase 2. No current handler needs it; the retrieval quality gap (description in episodic text) is already resolved.

---

## 2. Memory curation quality — `curate_memory` needs refinement

**What:** `curate_memory.py` runs nightly and makes one `CallType.CURATE_MEMORY` LLM call per agent to identify stale or redundant procedural rules. The current prompt and archival logic are first-pass.

**Known weaknesses:**

- The prompt asks the LLM to review all non-archived procedural rules for an agent in a single pass. For agents with many rules (50+), this risks truncation and degraded classification quality.
- The archival decision (`archived=True` in Qdrant payload) is irreversible within the current implementation — there is no restore path and no audit record of what was archived or why.
- The cron runs once per night regardless of how many tasks the agent has completed. A busy agent after 200 ticks needs curation more urgently than a fresh agent after 5.
- No signal is fed back about curation quality — whether the LLM correctly identified genuinely stale rules versus prematurely archiving still-relevant ones.

**Fix directions:**

- Break the curation call into domain-scoped batches rather than a full agent scan. This keeps the prompt focused and avoids truncation.
- Write a `CurationAuditEntry` to Postgres (similar to `ProceduralKnowledgeLog`) for each archived rule: `(agent_id, rule_id, rule_text, reason, archived_at)`. Restoring becomes `set_payload({"archived": False})` + deleting the audit row.
- Trigger curation when an agent's procedural collection exceeds a threshold size (e.g. 30 non-archived rules) rather than purely on a calendar schedule.

**Deferred because:** Phase 1. The nightly cron is a reasonable baseline; refinement is high-effort and requires observing real curation behaviour across a multi-tick run first.

---

## ~~3. No episodic write on task failure~~ ✅ Closed

Resolved in `execute_task.py` — both Phase 7 (success) and the exception handler (failure) call `_build_episodic_entry`, subject to the complexity gate (gap 5 below, also now closed).

---

## ~~4. `tool_trace` not available for episodic enrichment~~ ✅ Closed

Resolved in `_build_episodic_entry` — tool names are now included in the episodic text for both completed and failed paths (`Tools: web_search, code_execute`). The `TaskSnapshot` gap (handlers needing `tool_trace` from an event) remains deferred (see gap 1 above).

---

## ~~5. Episodic tier has no complexity gate — trivial tasks pollute retrieval~~ ✅ Closed

Resolved in `execute_task.py` Phase 7 and the failure handler. Both paths gate the episodic write on `(difficulty or 1.0) >= 3.0 or step_count > 3`, mirroring the `full_reflect` threshold already used by the rules stage.

---

## ~~6. Reflect job does not write to episodic~~ ✅ Closed

Resolved. `_stage_episodic` (stage 4 in `REFLECT_PIPELINE`) writes the factual execution record to `mem_episodic`. It builds the entry directly from `ReflectContext` fields — no LLM, no DB reads. This is the sole episodic write for a self-execute task; `execute_task` makes no memory writes.

Gated on `rctx.full_reflect` (same threshold as rules: difficulty ≥ 3.0 or step_count > 3). Covers both the completed and failed paths via `rctx.status` branch.

Known limitation: a retry produces a near-duplicate Qdrant point. Full idempotency requires stamping a point ID on the execution row — deferred.

---

## 7. Social memory fan-out at scale

**What:** `SocialMemoryHandler` writes one social memory observation per peer agent for every `task.completed` event. With N agents in a workspace, each completion triggers N−1 writes. At 50 agents and high task throughput this becomes 49 concurrent `store_social()` calls per completion, each an async Qdrant upsert.

**Why it matters:** Qdrant upserts are cheap individually but fan-out at this rate adds up under load. Each write also embeds the observation text via `aembed()` — an additional async call per write.

**Fix directions:**

- Batch all social writes for a single completion into one `client.upsert()` call with multiple `PointStruct` objects. Qdrant's batch upsert is significantly more efficient than N sequential upserts.
- Consider sampling: only agents whose social memory for the completing agent is older than T ticks (or who have fewer than K observations about that agent) receive a write. Agents with recent observations about a peer gain little from an immediate duplicate.

**Deferred because:** Phase 1 scale (≤50 agents) makes this a non-issue today. Flag for review when running production-scale workloads.

---

## Summary

| Gap | Impact | Phase | Status |
|-----|--------|-------|--------|
| Task `description` not in `TaskSnapshot` (handlers) | Low — no handler needs it yet | Phase 2 | Open |
| `curate_memory` prompt quality & audit trail | High — procedural tier health over long runs | Phase 2 | Open |
| No episodic write on failure | Medium — agent self-awareness | Phase 1 | ✅ Closed |
| `tool_trace` not available for episodic enrichment | Low–Medium | Phase 1 | ✅ Closed |
| Episodic complexity gate missing | Low — Phase 1 scale | Phase 1 | ✅ Closed |
| `key_learning` from reflect → episodic | Medium — richer retrieval | Phase 1 | ✅ Closed |
| Social memory fan-out at scale | Low — Phase 1 scale | Phase 3 | Open |
