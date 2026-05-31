# Reflection Pipeline — Gap Analysis & Proposed Redesign

**Status:** Under design — solution not yet finalised.
**Related gaps:** memory-gaps.md #3 (no failure episodic), #6 (key_learning), worker-gaps.md #16 (this document).
**Affected files:** `worker/jobs/reflect.py`, `worker/handlers/episodic_memory.py`, `worker/handlers/reflect_job.py`, `worker/jobs/execute_task.py`, `core/agents/scoring.py`, `core/intelligence/call_types.py`, `core/intelligence/prompts/reflect.py`, `core/intelligence/prompts/` (new files).

---

## 1. Current State

### 1.1 How quality is scored today

`score_outcome()` in `core/agents/scoring.py` runs synchronously inside `execute_task` Phase 6, immediately after the LangGraph graph returns. It is entirely heuristic:

| Component | Weight | Signal |
|---|---|---|
| Artifact presence | 0.60 | Did the graph produce any output at all? |
| Step efficiency | 0.25 | Did it finish well within the step limit? |
| Tool engagement | 0.15 | Did the agent invoke any tools? |

The score is written to `execution.quality_score` and injected into the `TaskUpdatedEvent` snapshot as a synthetic field. Everything downstream reads this number as ground truth.

**The fundamental problem:** the heuristic cannot assess whether the artifact answers the task. A graph that produces a long, confident, completely wrong response scores 0.95. A graph that produces a brief but accurate answer in one tool call scores ~0.73. The score measures execution mechanics, not output quality.

The `scoring.py` source already acknowledges this: `"When LLM-as-judge is ready, add it in worker/jobs/reflect.py using CallType.SCORE_DOCUMENT and overwrite this score on the TaskExecution row."` That extension point exists but has never been wired up.

---

### 1.2 How episodic memory is written today

`EpisodicMemoryHandler` is a `TaskUpdatedEvent` handler registered at worker startup (`startup.py:58`). It fires fire-and-forget on the in-process `EventBus` when:

- `status` changed to `"completed"`
- `execution_path == "self_execute"`
- `executing_agent_id` is set
- `quality_score` is set (non-None)

The text it writes is constructed entirely from snapshot fields:

```python
f"Completed {task_type} task: {title}. Domains: {domains}. Quality: {quality_score:.2f}."
```

The episode is embedded and upserted to Qdrant `mem_episodic`. The quality score in this episode is the **heuristic** score from `score_outcome()`.

---

### 1.3 How the reflect job is triggered today

`ReflectJobHandler` is a second `TaskUpdatedEvent` handler (registered at `startup.py:60`), with identical guards. It enqueues an ARQ `reflect` job, passing `quality_score` as a parameter.

The `reflect` job (`worker/jobs/reflect.py`):

1. Loads `Task`, `Agent`, `TaskExecution` from Postgres.
2. Determines `full_reflect`: `difficulty >= 3.0` OR `step_count > 3`.
3. If `full_reflect`: fetches existing procedural rules for the task's domain from Qdrant.
4. Calls LLM (`CallType.REFLECT`) with: task context, execution summary + tool_trace, quality_score, existing rules.
5. LLM returns `skill_deltas`, `generalised_rule`, `verdict`, `superseded_ids`.
6. Applies skill deltas to `agent.skills`, writes `SkillSnapshot` to Postgres.
7. If `full_reflect` and a rule was returned: upserts rule to Qdrant `mem_procedural`, archives superseded rules, writes `ProceduralKnowledgeLog` to Postgres.

---

### 1.4 How failure is handled today

`execute_task` writes `task.status = "failed"` and `execution.error = {type, message}` in its except block. The `task_logger.updated()` call on the failure path (`execute_task.py:279`) does **not** pass `executing_agent_id`, `execution_id`, or `execution_path`. Therefore:

- The `TaskUpdatedEvent` snapshot carries no `execution_id`.
- `ReflectJobHandler` cannot enqueue a reflect job (it guards on `execution_id is not None`).
- `EpisodicMemoryHandler` cannot write an episode (it guards on `quality_score is not None`, which is never set on failure).

**Result:** failed tasks teach nothing. No episodic record. No skill penalties. No procedural rule. The agent repeats the same failure.

---

## 2. The Gaps

### Gap A — Quality score is heuristic, not semantic

`score_outcome()` cannot assess whether an artifact answers its task. It scores execution mechanics. The heuristic is a proxy that fails silently on agents that produce plausible-but-incorrect output — which is precisely the failure mode that matters for emergence. Agents accumulate skill points for producing text, not for solving problems.

**Impact on emergence:** Skill specialisation and influence credit both flow from `quality_score`. If the score does not reflect actual output quality, agents that confidently produce wrong answers rise through the influence hierarchy just as fast as agents that produce correct ones. The coordinator pattern cannot emerge reliably on a corrupted quality signal.

---

### Gap B — Episodic and reflect are temporally decoupled but share a score

`EpisodicMemoryHandler` fires immediately from the event with the heuristic score. The `reflect` job runs asynchronously (seconds or minutes later) and has a better context. If a future judge call in `reflect` determines the actual quality was 0.3, not 0.87, the episodic record already in Qdrant is wrong. There is no update path — Qdrant entries are upserted by random UUID, so reflect cannot overwrite the handler's record without tracking the point ID.

---

### Gap C — Single reflect LLM call carries too many responsibilities

The current `CallType.REFLECT` prompt asks the LLM to simultaneously:
- Evaluate skill performance across multiple domains
- Determine delta magnitudes
- Extract a generalised procedural rule
- Assess whether the rule supersedes, complements, or contradicts existing rules
- Provide superseded point IDs to archive

This is five distinct reasoning tasks in one prompt. Signal quality degrades as the prompt grows. A supersession decision that requires comparing a new rule against 15 existing rules while simultaneously estimating skill deltas is well above the reasoning budget of a single call.

---

### Gap D — No failure reflection

Failure is the most informative learning signal. An agent that attempted a security task, used the wrong tools, and failed should record: an episodic entry (what was attempted), a skill penalty (the domain proved harder than the bid implied), and a procedural rule ("avoid X approach for Y task type"). None of these happen today.

---

### Gap E — Violation of single-responsibility in the post-execution layer

Today, `EpisodicMemoryHandler` and `ReflectJobHandler` are separate handlers that share identical guards and produce related but not coordinated outputs. They are not composed — `EpisodicMemoryHandler` does not know what `reflect` determined, and `reflect` does not know what episodic wrote. The fact that they share the same event and near-identical guards is a design smell: they are doing two halves of one job.

---

## 3. Proposed Solution — Reflect as a Unified Post-Execution Pipeline

> **Decision not yet finalised.** The shape below represents the leading design candidate. Key questions are called out in section 4.

### 3.1 Core principle

`reflect` becomes the **single owner of all post-execution memory and learning writes**. `EpisodicMemoryHandler` is removed as a standalone handler. All memory writes flow through the ARQ job after a sequenced pipeline of focused operations.

`ReflectJobHandler` becomes the only `TaskUpdatedEvent` handler for post-execution learning, and it fires on both `"completed"` and `"failed"`.

---

### 3.2 Pipeline stages

```
reflect (ARQ job)
  │
  ├── Stage 1: Judge
  │     Input:  task (title, description, required_skills, difficulty)
  │             execution (artifact, tool_trace, error)
  │             heuristic_score (hint only)
  │     Output: judged_score [0.0–1.0], judge_reasoning
  │     Write:  execution.quality_score overwritten in Postgres
  │
  ├── Stage 2: Episodic write
  │     Input:  task context + judged_score + execution path
  │             Success: builds rich text from title, description, domains, judged_score
  │             Failure: builds failure text from title, error type, what was attempted
  │     Output: Qdrant mem_episodic point
  │     Gate:   full_reflect or difficulty >= 2 (trivial tasks still excluded)
  │
  ├── Stage 3: Skill deltas
  │     Input:  task context, judged_score, tool_trace
  │     LLM:    CallType.REFLECT (skills-only prompt, reduced scope vs. current)
  │     Output: skill_deltas dict
  │     Write:  agent.skills (logistic growth), SkillSnapshot to Postgres
  │     Gate:   always runs (skill updates apply to trivial tasks too)
  │
  └── Stage 4: Procedural rule
        Input:  task context, judged_score, existing domain rules
        LLM:    CallType.REFLECT_RULE (new — separated from skill call)
                Success path: "what generalised rule does this execution establish?"
                Failure path: "what should be avoided / what went wrong?"
        Output: generalised_rule, verdict, superseded_ids
        Write:  Qdrant mem_procedural + ProceduralKnowledgeLog
        Gate:   full_reflect only (difficulty >= 3 or steps > 3)
```

Each stage receives exactly the inputs it needs. No stage returns to a previous stage. No stage knows about other stages.

---

### 3.3 Changes to `execute_task` failure path

The failure `task_logger.updated()` call at `execute_task.py:279` must be updated to pass `executing_agent_id`, `execution_id`, and `execution_path` when `execution` is not None:

```python
# Current
await task_logger.updated(before_failed, task)

# Proposed
await task_logger.updated(
    before_failed, task,
    executing_agent_id=agent.id if execution is not None else None,
    execution_id=execution.id if execution is not None else None,
    execution_path="self_execute",
)
```

When `execution is None` (Phase 2 never committed), the snapshot carries no execution fields and `ReflectJobHandler` skips enqueue — the guard on `execution_id is not None` handles this correctly.

---

### 3.4 `CallType` additions

```python
class CallType(str, Enum):
    ...
    JUDGE        = "judge"          # LLM-as-judge: scores actual output quality
    REFLECT_RULE = "reflect_rule"   # Procedural rule extraction only (split from REFLECT)
```

`REFLECT` is kept for the skills-only call (stage 3). `SCORE_DOCUMENT` (already in the enum) is removed or aliased — `JUDGE` supersedes it.

---

### 3.5 New prompt files

| File | Responsibility |
|---|---|
| `core/intelligence/prompts/judge.py` | Receives task + artifact + heuristic hint. Returns `judged_score`, `judge_reasoning`. No skill logic. |
| `core/intelligence/prompts/reflect.py` | Narrowed: skills-only. Receives task context + judged_score + tool_trace. Returns `skill_deltas` only. |
| `core/intelligence/prompts/reflect_rule.py` | New. Receives task context + judged_score + existing rules. Returns `generalised_rule`, `verdict`, `superseded_ids`. Success and failure are separate system prompts, selected by the caller. |

Each file has a single `build_prompt()` and `parse()`. No file knows about another file's output. Prompt logic does not bleed between stages.

---

### 3.6 Handler changes

**`ReflectJobHandler`:**
- Guard loosened: fires on `status in {"completed", "failed"}`.
- Passes `status` and `error` (from snapshot or loaded from execution) to the enqueued job.
- `EpisodicMemoryHandler` binding removed from `startup.py`.

**`EpisodicMemoryHandler`:**
- Removed entirely. Episodic writes are owned by the reflect pipeline.

---

### 3.7 SoC and decoupling properties of this design

| Concern | Where it lives | What it does not do |
|---|---|---|
| Execution scoring (heuristic baseline) | `core/agents/scoring.py` | No LLM, no DB writes, no memory |
| Semantic quality judgement | `worker/jobs/reflect.py` Stage 1 + `prompts/judge.py` | No skill updates, no memory writes |
| Episodic memory write | `worker/jobs/reflect.py` Stage 2 + `core/memory/agent_memory.py` | No LLM calls, no skill updates |
| Skill delta computation | `worker/jobs/reflect.py` Stage 3 + `prompts/reflect.py` | No memory writes, no rule extraction |
| Procedural rule extraction | `worker/jobs/reflect.py` Stage 4 + `prompts/reflect_rule.py` | No skill updates, no episodic writes |
| Memory storage | `core/memory/agent_memory.py` | No domain logic, no LLM calls |
| Bus / event triggering | `worker/handlers/reflect_job.py` | No execution logic, no memory access |

The `reflect` job is the **coordinator** of the pipeline: it sequences stages, threads data between them, and owns the single DB session for the final write. It does not implement any stage's logic itself — each stage is a function call to a focused module.

---

## 4. Open Questions and Design Tensions

### Q1 — Should the judge always run, or only on `full_reflect` tasks?

**Option A (always):** Every self-execute completion gets LLM-as-judge. More accurate quality signals across the board. Higher token cost — every task completion now costs one extra LLM call.

**Option B (full_reflect gate):** Judge only runs when `difficulty >= 3.0` or `step_count > 3`. Trivial tasks fall back to the heuristic. Saves tokens at the cost of a less uniform quality signal.

**Tension:** Skill decay is applied per-task in Phase 6. If judge only runs on hard tasks, easy tasks get heuristic scores for skill recovery but not for harder tasks. This creates an asymmetry in the quality signal that could distort skill convergence.

---

### Q2 — Should `key_learning` be an additional episodic write or the primary one?

The current episodic handler writes a deterministic text string from snapshot fields (no LLM). Memory-gaps.md gap #6 proposes adding a `key_learning` field from the reflect LLM call — an agent-perspective distillation of what the execution taught.

**Option A:** Two episodic writes — one deterministic factual entry (what happened), one LLM-extracted insight entry (what it taught). Both in `mem_episodic`, distinguished by `source: "reflect"` vs `source: "execution"`.

**Option B:** One episodic write per execution, LLM-generated, from the judge+reflect context. The richer LLM-derived episode replaces the deterministic one.

**Option C:** Keep deterministic episodic write (Stage 2 as described) and separately add `key_learning` to Stage 4 (procedural rule extraction) since it runs the LLM anyway — trivial to add one more output field.

**Tension:** Option B produces richer episodes but adds latency to the episodic record. Option A writes two records per task, complicating retrieval — agents would surface both the factual entry and the insight, potentially confusing the semantic search.

---

### Q3 — Where does the judged score live while stages 2–4 run?

The judge writes `judged_score` back to `execution.quality_score` in Postgres (Stage 1 DB write). Stages 2–4 read from the in-memory result, not from a DB re-read. This means the corrected score is available in-memory for the remainder of the pipeline but the Postgres row has already been updated before stages 2–4 commit their writes.

**Risk:** If Stage 2, 3, or 4 fail after Stage 1 commits, the execution row has a judged score but no episodic/skill/procedural record. The reflect job is not retried by default — ARQ treats `reflect` as best-effort. A failure mid-pipeline produces an inconsistent state: better quality score, no memory updates.

**Option A:** Batch all writes into a single commit at the end of Stage 4. Judged score is written once with everything else. Risk: if judge succeeds but Stage 4 LLM fails, the quality score is never updated.

**Option B:** Accept the inconsistency. Judge write is idempotent — if the job retries from the start, the judge re-runs (same result), and subsequent stages re-run too. ARQ `max_tries` on the reflect job handles this.

**Option C:** Stage 1 writes the judged score; stages 2–4 are wrapped in a single try/except that logs failures without re-raising — partial write is acceptable, the job does not fail if a stage fails.

---

### Q4 — Failure path: what is the judge's input when there is no artifact?

On failure, `execution.artifact` is None. The judge prompt receives an error string instead of an artifact. This is a fundamentally different input contract from the success path.

**Options:**
- Single judge prompt with conditional branches for success/failure — one `build_prompt()` handles both.
- Two judge prompts: `judge_success.py` and `judge_failure.py` — cleaner SoC but more files.
- Skip the judge entirely on failure and fix `quality_score = 0.0` — failure quality is always zero; no LLM needed to determine this. Stage 2 (episodic) and Stage 3 (skill penalties) can run without a judge score. Stage 4 runs with a failure-specific prompt.

**Tension:** Skipping the judge on failure is simpler but inconsistent with the principle that the judge determines quality. A task that ran for 15 steps, used 6 tools, and failed at the final step is qualitatively different from a task that crashed on the first tool call. A fixed 0.0 erases that distinction.

---

### Q5 — Should stages 3 and 4 be separate LLM calls?

Separating skill deltas and procedural rule extraction into two calls (`REFLECT` + `REFLECT_RULE`) addresses the single-call overload problem (Gap C). But it doubles the LLM cost per non-trivial completion.

**Option A (two calls, as proposed):** Clear SoC. Each prompt is focused and shorter. Better signal quality per call. Higher token cost.

**Option B (combined call, current approach):** One call, lower cost. The prompt must encode both skill-assessment and rule-extraction reasoning. Signal quality suffers as existing rules list grows.

**Option C (two calls but cached system prompts):** Use prompt caching (`cache_control: ephemeral`) on the system prompt for the skills call since it changes infrequently. Reduces effective token cost of the second call significantly at scale.

---

## 5. Constraints and Non-Negotiables

These are not open questions — they constrain any solution:

1. **No LLM calls in handlers.** `EpisodicMemoryHandler` or any replacement handler must not call the LLM. All LLM calls for reflection go through the ARQ job.

2. **No DB reads in handlers.** Handlers fire from event snapshots. They do not open sessions.

3. **All stages in one ARQ job.** The reflect pipeline is one job. Chaining multiple ARQ jobs (`judge → reflect → episodic`) introduces coordination failure modes — if `judge` succeeds and `reflect` is never enqueued, the quality score update is orphaned. A single job with internal stages is safer and simpler.

4. **`score_outcome()` stays.** The heuristic must remain as a synchronous, dependency-free baseline for two reasons: (a) it runs on the critical path as the provisional score; (b) it is the judge's baseline hint input. It is not replaced — it is supplemented.

5. **Prompts stay in `core/intelligence/prompts/`.** One file per call type. No prompt logic in `worker/` files.

6. **`full_reflect` gate is preserved.** Low-difficulty, low-step tasks do not get procedural rule extraction regardless of what the judge scores them. This gate exists to prevent procedural memory pollution from trivial completions.

7. **Failure path requires execution row.** The reflect job only enqueues when `execution_id` is present on the snapshot. If Phase 2 never committed (execution row does not exist), no reflect job is enqueued — there is nothing to reflect on.

---

## 6. Tasks

The following tasks need to be completed to implement this gap, in dependency order. The solution is not yet finalised — tasks marked **[BLOCKED on Q#]** depend on decisions in section 4.

### Infrastructure changes (no design dependencies)

- [ ] **T1** — Add `JUDGE` and `REFLECT_RULE` to `CallType` enum in `core/intelligence/call_types.py`. Add routing entries for both in `routing_config.py` defaults.
- [ ] **T2** — Fix `execute_task.py:279` failure path: pass `executing_agent_id`, `execution_id`, and `execution_path` to `task_logger.updated()` when `execution is not None`.
- [ ] **T3** — Update `ReflectJobHandler` to fire on `status in {"completed", "failed"}`. Pass `status` to the enqueued job.

### New prompt files

- [ ] **T4** — Create `core/intelligence/prompts/judge.py`: `JudgeResponse(judged_score, reasoning)`, `build_prompt()`, `parse()`. Input: task context, artifact or error, heuristic hint. **[BLOCKED on Q4]** — confirm whether success and failure use one prompt or two.
- [ ] **T5** — Narrow existing `core/intelligence/prompts/reflect.py` to skills only: `ReflectResponse(skill_deltas)`. Remove `generalised_rule`, `verdict`, `superseded_ids`.
- [ ] **T6** — Create `core/intelligence/prompts/reflect_rule.py`: `ReflectRuleResponse(generalised_rule, verdict, superseded_ids)`, `build_prompt(status)` branching on success/failure system prompts, `parse()`.

### Reflect job restructure

- [ ] **T7** — Restructure `worker/jobs/reflect.py` into the four-stage pipeline. Stage 1: judge call. Stage 2: episodic write. Stage 3: skills LLM call + agent update. Stage 4: rule extraction LLM call + procedural write. **[BLOCKED on Q1, Q3]** — confirm judge gate and write-commit strategy.
- [ ] **T8** — Add failure path branch in Stage 2: different episodic text for failed tasks; `quality_score` defaults to judge output or 0.0 on failure.
- [ ] **T9** — Add failure path branch in Stage 4: use failure prompt variant in `reflect_rule.py`; still gate on `full_reflect`.

### Handler and startup changes

- [ ] **T10** — Remove `EpisodicMemoryHandler` binding from `worker/startup.py`. Remove the handler file (or archive in a dead-code pass if the team prefers).
- [ ] **T11** — Update `startup.py` `ReflectJobHandler` binding: confirm it is the only post-execution memory handler.

### Validation

- [ ] **T12** — Run a single-agent task through the full pipeline and verify: judged score written to `execution.quality_score`; episodic entry in Qdrant with judged score; skill delta applied with logistic growth; procedural rule in Qdrant (if `full_reflect`). Check Postgres `ProceduralKnowledgeLog` for the rule.
- [ ] **T13** — Run a failing task and verify: episodic failure entry written; skill penalty applied; failure procedural rule written (if `full_reflect`). Verify no `quality_score` is left as the heuristic value on the execution row.
- [ ] **T14** — Verify `score_outcome()` result is still being written to `execution.quality_score` in Phase 6 as the provisional score, and that the judge overwrites it in Stage 1. If Stage 1 is skipped (Q1 option B), confirm the heuristic score stays.

---

## 7. Impact on Related Gaps

Closing this gap partially or fully resolves several existing tracked gaps:

| Existing gap | Resolution |
|---|---|
| memory-gaps.md #3 — No episodic write on failure | Closed: Stage 2 handles failure path |
| memory-gaps.md #6 — `key_learning` from reflect → episodic | Partially addressed: Stage 2 writes richer episodic text; full `key_learning` is **[BLOCKED on Q2]** |
| memory-gaps.md #1 — Task description not in episodic text | Addressed: Stage 2 has access to full `task.description` from the DB read in reflect (no snapshot constraint) |
| worker-gaps.md #scoring — heuristic quality score | Closed: judge stage replaces heuristic as the primary signal |

---

## 8. Emergence Implications

The quality signal is the substrate on which emergence runs. Every mechanism that produces differentiation between agents — skill specialisation, influence credit, bid scoring, coordinator selection — is downstream of `quality_score`. A heuristic score that rewards artifact production over task completion creates a selection pressure toward verbose, confident, wrong agents.

The reflect pipeline redesign is not a quality-of-life improvement. It is a correctness fix for the signal that drives emergence. Without it, skill trajectories converge on agents that produce text well, not agents that solve problems well. The coordinator pattern (high-influence agents decomposing and delegating, low-influence agents self-executing to build track records) cannot emerge reliably on a corrupted signal.

Failure reflection compounds this. An agent that fails at a task and receives no penalty can repeat the same failure indefinitely while its influence drifts upward on other tasks. Failure episodes and skill penalties are the mechanism by which agents that over-bid on tasks they cannot complete are pushed back down the influence hierarchy.