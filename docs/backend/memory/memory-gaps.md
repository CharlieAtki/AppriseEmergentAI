# Memory Layer — Gaps & Future Work

Tracks known gaps, design limitations, and deferred improvements in the three-tier memory system (episodic, procedural, social). Ordered roughly by impact.

Cross-cutting gaps (audit log, API→Redis bridge, test coverage) are tracked in [`docs/eventing/event-bus-gaps.md`](../eventing/event-bus-gaps.md).

---

## 1. Task `description` not available for memory writes

**What:** `Task.description` is not included in `TaskSnapshot`. The episodic write text currently uses only `title`, `task_type`, and `domain_tags`. The reflect prompt uses `task.description` (loaded directly from the DB in `reflect.py`), but `EpisodicMemoryHandler` fires from a snapshot and has no access to it.

**Why it matters:** Description is the richest natural-language signal for semantic retrieval. An embedding built from `"Completed code task: Implement JWT auth. Domains: security."` is weaker than one that also encodes what the task actually required. This affects both episodic retrieval quality (agents surfacing relevant past experience mid-execution) and potentially UI display if episode records are ever surfaced to users.

**Fix:** Add `description: str | None` to `TaskSnapshot` as a fourth synthetic field alongside `executing_agent_id`, `quality_score`, `execution_id`, and `execution_path`. Pass it from `execute_task` via `task_logger.updated()`. The episodic text becomes:

```
"Completed code task: Build JWT auth endpoint — validates tokens and returns user profile. Domains: security, api. Quality: 0.85."
```

**Deferred because:** Phase 1. Description can be long; embedding quality gains need to be validated against the added payload size in Qdrant.

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

## 3. No episodic write on task failure

**What:** `EpisodicMemoryHandler` only fires when `event.state.status == "completed"`. Failed tasks produce no episodic record.

**Why it matters:** Failure is informative. An agent that attempted a security task and failed should remember that — it informs future bid scoring and self-selection. "Attempted code task: Implement OAuth flow. Domains: security, api. Failed (quality: 0.0)" is signal, not noise.

**Fix:** Lower the guard from `status == "completed"` to `status in {"completed", "failed"}`. For failed tasks, `quality_score` is `None` (the task never reached scoring), so the text needs a conditional branch:

```python
quality_str = f"Quality: {event.state.quality_score:.2f}." if event.state.quality_score is not None else "Failed."
```

The payload stores `quality_score: None` for failed episodes, which is already a valid Qdrant value.

**Deferred because:** Phase 1. Requires verifying that failed-task snapshots carry sufficient metadata (they currently drop `execution_path` and other fields in the failure path of `execute_task`).

---

## 4. `tool_trace` not available for episodic enrichment

**What:** The episodic text could include a summary of tools the agent used (e.g. `"Tools: web_search, code_execute"`), giving future retrievals a stronger signal for tool-use similarity. `tool_trace` is on `TaskExecution` but not on `TaskSnapshot`.

**Why it matters:** Two tasks with the same title but different tool use patterns represent genuinely different execution experiences. An agent searching for "how did I solve this last time" benefits from knowing whether the prior approach involved search, code execution, or direct LLM reasoning.

**Fix (Option A):** Add `tool_names: tuple[str, ...] | None` as a synthetic field on `TaskSnapshot`, derived from `execution.tool_trace` and passed through `task_logger.updated()` from `execute_task` Phase 6 (where the execution object is still in memory).

**Fix (Option B):** Add `execution_id` is already on the snapshot — `EpisodicMemoryHandler` could query `TaskExecution` for the tool trace. This adds one DB read back into a handler we just cleaned up, so Option A is preferred.

**Deferred because:** Phase 1. Adds a snapshot field and a call-site change across `execute_task`, `_finalise_execution`, and the logger. Non-trivial for marginal Phase 1 gain.

---

## 5. Episodic tier has no complexity gate — trivial tasks pollute retrieval

**What:** Every self-execute completion writes an episodic entry, regardless of task difficulty or step count. A difficulty-1 task completed in one step produces the same episodic footprint as a difficulty-4 multi-tool execution.

**Why it matters:** Over many ticks, the episodic collection fills with low-signal entries. When an agent searches for relevant past experience on a complex task, the top-k results may be dominated by trivial completions that share domain tags but carry no actionable insight.

**Fix:** Mirror the complexity gate already used in `reflect.py`: only write episodic entries for tasks where `difficulty >= 2` or `step_count > 1`. Trivial tasks contribute to skill score updates (via `InfluenceUpdateHandler`) but not to the memory tier.

This requires `difficulty` on the snapshot (already there) but `step_count` is derived from `tool_trace` (see gap 4 above).

**Deferred because:** Phase 1. The gate threshold needs calibration against real run data. Premature gating risks gaps in the episodic record that harm retrieval in ways that are hard to detect.

---

## 6. Reflect job does not write to episodic — `key_learning` gap

**What:** The Hermes analysis recommends that for non-trivial tasks, the reflect job extracts a `key_learning` — a one-sentence agent-perspective distillation of what the specific execution taught — and writes it to episodic memory. Currently `reflect.py` writes only to procedural (`store_procedure()`) and `ProceduralKnowledgeLog`.

**The distinction:**

| | Episodic entry (current) | Procedural entry (reflect) | Missing: key_learning |
|---|---|---|---|
| Content | Factual: what happened | Generalised: what to do in this domain | Specific insight: what *this* execution taught *this* agent |
| Source | Snapshot fields (no LLM) | LLM reflection | LLM reflection |
| Gate | All self-execute completions | `full_reflect` only (difficulty ≥ 3 or steps > 3) | `full_reflect` only |

**Fix:** Add `key_learning: str` to `ReflectResponse`. Update `build_prompt()` to request it. In `reflect.py`, after parsing the response, call `wctx.memory.store_episode()` with `key_learning` as the text and `source: "reflect"` in the payload to distinguish it from the handler-written entry.

**Deferred because:** Phase 1. The episodic enrichment (gap 1 above — adding description) should come first; richer factual entries may reduce the need for LLM-extracted insights at this stage.

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

| Gap | Impact | Phase |
|-----|--------|-------|
| Task `description` not in snapshot/episodic text | Medium — retrieval quality | Phase 2 |
| `curate_memory` prompt quality & audit trail | High — procedural tier health over long runs | Phase 2 |
| No episodic write on failure | Medium — agent self-awareness | Phase 2 |
| `tool_trace` not available for episodic enrichment | Low–Medium | Phase 2 |
| Episodic complexity gate missing | Low — Phase 1 scale | Phase 3 |
| `key_learning` from reflect → episodic | Medium — richer retrieval | Phase 2 |
| Social memory fan-out at scale | Low — Phase 1 scale | Phase 3 |
