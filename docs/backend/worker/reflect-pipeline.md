# Reflection Pipeline

Post-execution learning for self-execute tasks. After an agent completes or fails a task,
the reflection pipeline updates its skill profile and extracts procedural knowledge for
future retrieval.

---

## Design principles

**One LLM call.** The pipeline makes a single `CallType.REFLECT` call. Everything else
is algorithmic — skill delta magnitudes are computed from the quality score, episodic
memory is assembled from data already in hand, and rule persistence is a straight DB write.

**The quality score is never overwritten.** `score_outcome()` runs at execution time and
produces a deterministic value in `[0.0, 1.0]`. That value is the authoritative signal
throughout the pipeline. No LLM judge replaces it.

**The LLM classifies, not measures.** The model's only job is to identify which skill
domains were exercised and extract a reusable procedural rule. Float delta magnitudes
are computed as `0.08 × (quality_score − current_skill)` — grounded in the quality
signal, not the model's priors.

---

## Trigger

`ReflectJobHandler` listens for `TaskUpdatedEvent` on the in-process `EventBus`. When
a `self_execute` task transitions to `"completed"` or `"failed"`, it enqueues an ARQ
`reflect` job with `execution_id`, `agent_id`, `task_id`, `workspace_id`, and `status`.

The reflect job is also enqueued by `RollupSubtaskHandler` when a decomposed parent task
rolls up to completion.

---

## Episodic write (before the reflect job)

Before the reflect job is enqueued, `execute_task` Phase 7 writes an episodic memory
entry directly to Qdrant's `mem_episodic` collection. This write is:

- **No LLM.** Built from `task.*`, `execution.*`, and `quality` — all already in memory.
- **Guarded.** Wrapped in `try/except` so Qdrant unavailability never marks a completed
  task as failed.
- **Factual.** Records task type, title, description excerpt, artifact excerpt, domain
  tags, quality score, and status. Retrievable by future executions via semantic search.

For failed tasks, the equivalent write happens in the `execute_task` exception handler,
also guarded.

**Source:** `worker/jobs/execute_task.py` — `_build_episodic_entry()`, Phase 7

---

## Reflect job

`worker/jobs/reflect.py`

```
1. Load Task, Agent, TaskExecution in one session → session closes
2. Idempotency check: if execution.reflect_completed_at is set → return
3. Build ReflectContext (frozen snapshot, no live ORM references)
4. Compute full_reflect = (difficulty >= 3.0) or (step_count > 3)
5. Run ReflectionManager.run(rctx, span)
6. Stamp reflect_completed_at
```

**Idempotency gap:** stages are not individually idempotent. If the process dies after
the pipeline runs but before the stamp is written, ARQ retries will re-run all stages.
Episodic writes (which happen in `execute_task`, not here) are not deduplicated.

---

## Pipeline stages

`worker/reflection/stages.py` | `worker/reflection/manager.py`

```
Stage 1: reflect   — always runs
Stage 2: skills    — always runs
Stage 3: rules     — gated: only when full_reflect=True
```

Per-stage failures are caught and logged — a failing stage does not abort the pipeline.
Stage names are appended to `PipelineResult.stages_run` (success) or
`PipelineResult.stages_failed` (exception) for observability.

---

### Stage 1 — `_stage_reflect` (one LLM call)

Builds a `TaskContext` and `ResultContext` from `rctx`, then makes one `CallType.REFLECT`
call. Two paths:

**Lightweight** (`full_reflect=False`):

The prompt asks for:
- `skill_domains` — skill names from `required_skills` that were exercised
- `new_skill_suggestions` — skill names *not* in `required_skills` that this task revealed

Short prompt, no rule extraction. Haiku-class model is sufficient.

**Full** (`full_reflect=True`):

Before the LLM call, existing procedural rules are fetched from Qdrant:
- Queries each `domain_tags` key separately via `retrieve_procedures_for_domain()`
- Deduplicates by Qdrant point ID across all tag queries
- Falls back to `task_type` when no domain tags exist

The prompt additionally asks for:
- `generalised_rule` — completed tasks: HOW-TO; failed tasks: WHAT-TO-AVOID.
  **Constraint:** must reference a specific tool, error type, code pattern, or domain
  artifact from the trace. Generic advice must return `null`.
- `verdict` — `"supersedes"`, `"complements"`, or `"contradicts"` relative to the
  injected existing rules. `null` if none are relevant.
- `superseded_ids` — Qdrant point IDs of rules this one replaces.

The parsed `ReflectOutput` is written onto `PipelineResult` for downstream stages.

**Source:** `core/intelligence/prompts/reflection/reflect.py` — `build_prompt()`, `ReflectOutput`

---

### Stage 2 — `_stage_skills` (algorithmic, no LLM)

Reads `result.skill_domains` and `result.new_skill_suggestions` from Stage 1.

**Delta computation:**
```python
delta = 0.08 × (heuristic_score − current_skill)   # compute_delta_magnitude()
new   = apply_skill_delta(current, delta)            # logistic growth bounds
```

Positive when the agent outperformed its current level; negative when below. Logistic
growth means gains taper as a skill approaches 1.0 and penalties taper as it approaches 0.0.

**Guards:**
- Only applies deltas to names present in `rctx.required_skills`. Names outside that set
  belong in `new_skill_suggestions` — this prevents LLM prompt slippage from writing
  arbitrary strings into the agent's skill profile.
- New skill seeds write at `0.1` only if the key is absent entirely (`skill = 0.0` is not
  overwritten).
- Skips the DB write entirely if both lists are empty.

**Concurrency:** the `Agent` row is loaded with `with_for_update=True`. If two reflect
jobs run for the same agent simultaneously, the second blocks until the first commits,
then reads the already-updated skills and applies its own deltas on top.

Also writes a `SkillSnapshot` row for the observability audit trail.

**Source:** `core/coordination/skills.py` — `compute_delta_magnitude()`, `apply_skill_delta()`

---

### Stage 3 — `_stage_rules` (no LLM, gated)

Gate: only runs when `rctx.full_reflect=True`. Returns immediately if `result.rule` is
`None` — Stage 1 may decline to extract a rule even on full_reflect executions.

**Dual-write order** (enforced structurally):

1. **Postgres first** — `ProceduralKnowledgeLog` is the durable audit trail. If Qdrant
   is unavailable, the rule is not lost.
2. **Qdrant second** — `memory.store_procedure()` is called with `session=None` to
   prevent it from writing its own `ProceduralKnowledgeLog` row (that would duplicate
   the Postgres write above and violate write order).

`store_procedure` archives superseded rules in Qdrant by setting `archived=True` on each
`superseded_ids` point. Archived entries are excluded from all future `_base_filter`
retrievals.

Storage domain is `_primary_domain(rctx)`: first `domain_tags` key → `task_type` →
`"general"`.

---

## Data flow summary

```
execute_task Phase 6
  score_outcome() → quality (float)
  execution.quality_score = quality  ← written to DB, never overwritten

execute_task Phase 7
  _build_episodic_entry(task, execution, "completed", quality)
    → memory.store_episode()  [guarded: Qdrant failure does not fail the task]
  stream_logger.task_completed()
    → ReflectJobHandler fires → enqueue_job("reflect", ...)

reflect job
  ReflectContext (frozen snapshot)
    heuristic_score = execution.quality_score
    full_reflect    = difficulty >= 3.0 or step_count > 3

  Stage 1 — _stage_reflect
    [if full_reflect] Qdrant: retrieve existing rules by domain_tags
    LLM: CallType.REFLECT → ReflectOutput
      skill_domains:         ["python", "api_design"]
      new_skill_suggestions: ["async_debugging"]
      generalised_rule:      "..." or null
      verdict:               "supersedes" | "complements" | "contradicts" | null
      superseded_ids:        ["qdrant-point-id", ...]

  Stage 2 — _stage_skills
    for each skill in skill_domains (clamped to required_skills):
      delta = 0.08 × (quality - current)
      new   = apply_skill_delta(current, delta)
    for each skill in new_skill_suggestions (if absent):
      agent.skills[skill] = 0.1
    Agent row updated under FOR UPDATE lock
    SkillSnapshot written

  Stage 3 — _stage_rules [gate: full_reflect and result.rule is not None]
    Postgres: ProceduralKnowledgeLog inserted
    Qdrant:   store_procedure(session=None)
              + archive superseded rules

  stamp: execution.reflect_completed_at = now()
```

---

## Key types

| Type | Location | Purpose |
|---|---|---|
| `ReflectContext` | `core/intelligence/reflection/types.py` | Frozen snapshot passed through all stages |
| `PipelineResult` | `core/intelligence/reflection/types.py` | Mutable accumulator; stages read/write |
| `ReflectOutput` | `core/intelligence/prompts/reflection/reflect.py` | Parsed LLM response |
| `ExistingRule` | `core/intelligence/prompts/reflection/reflect.py` | Qdrant rule injected for supersession |
| `ReflectionManager` | `worker/reflection/manager.py` | Sequences stages, owns LLMRouter + AgentMemory |
| `PipelineStage` | `core/intelligence/reflection/pipeline.py` | Declarative stage entry (name, fn, gate) |

---

## Full_reflect gate

| Condition | Path |
|---|---|
| `difficulty < 3.0` and `step_count ≤ 3` | Lightweight: skill classification only |
| `difficulty >= 3.0` or `step_count > 3` | Full: + rule extraction, supersession |

`step_count` is `len(execution.tool_trace)` at reflect job load time. Both conditions
are evaluated in `reflect.py` and stored on `rctx.full_reflect`. The rules stage gate
and the prompt path both read from this single field.

---

## LLM call budget per task (self-execute path)

| Phase | Calls | Model |
|---|---|---|
| Evaluate | 1 | Haiku |
| Execute (ReAct loop, N steps) | N | Sonnet |
| Reflect (lightweight) | 1 | Sonnet |
| Reflect (full, difficulty ≥ 3 or steps > 3) | 1 | Sonnet |

Reflect is always exactly 1 call regardless of path.