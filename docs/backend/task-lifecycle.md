# Task Lifecycle — End-to-End Flow

This document traces the complete journey of a task from the moment a customer POSTs it to
the API through execution, RL updates, memory writes, and the emergence signals that feed
the observability dashboard. It covers all three execution paths: self-execute, decompose,
and CFP.

Read the **Backend Developer Reference** and **Worker & Core Deep Dive** first. This document
assumes you know the three-process split and the difference between the in-process `EventBus`
and the cross-process `RedisBus`.

---

## Architecture recap — the two event systems

Before tracing the flow, the distinction between the two buses matters for understanding
what fires when:

| Bus | Class | Transport | Who publishes | Who consumes |
|-----|-------|-----------|---------------|--------------|
| In-process | `EventBus` | asyncio | `TaskActivityLogger`, `TaskStreamLogger` callbacks | `EventHandler` subclasses bound at startup |
| Cross-process | `RedisBus` | Redis Streams | `TaskStreamLogger` | `TaskStreamSubscriber` (bridges back to `EventBus` in each worker) |

**Key invariant:** domain code never calls `bus.apublish()` directly. The only way an event
is produced is through a logger (`TaskActivityLogger` for in-process, `TaskStreamLogger` for
cross-process).

---

## Phase 0 — API ingestion

**Entry point:** `POST /workspaces/{id}/tasks`
**File:** `api/api/routers/tasks.py`

1. Auth middleware resolves `Clerk` JWT or `X-API-Key` → maps to internal `(org_id, workspace_id)`.
2. Router validates `CreateTaskRequest` (Pydantic). Idempotency key checked — duplicate
   keys return the existing task.
3. A `Task` row is written with `status="pending"`. The API returns `202 Accepted` with
   the task ID immediately — the customer does not wait for execution.
4. `enrich_and_release` is called (still inside the API process). This is the only LLM
   call the API is permitted to make. It:
   - Runs rule-based enrichment first (fast, deterministic: task_type, skill inference from
     title patterns).
   - If rules are insufficient, calls `LLMRouter` with `CallType.ENRICH` to infer
     `required_skills`, `difficulty`, `task_type`, and `domain_tags`.
   - Transitions task to `status="open"` and commits.
5. `TaskActivityLogger.updated()` fires a `TaskUpdatedEvent` on the **in-process** `EventBus`.
   (No handlers in the API process consume this — the API's EventBus is wired for its own
   side effects only, e.g. cache invalidation.)
6. `TaskStreamLogger.task_created()` publishes `task.created` to **Redis Streams**
   (`stream:task`). This is the durable handoff to the worker.

```
Customer POST
  → validate
  → Task(status="pending") → DB
  → 202 returned
  → enrich_and_release
      → rule engine + optional LLM
      → Task(status="open") → DB commit
      → stream:task ← task.created published
```

---

## Phase 1 — Bidding and reservation (worker subscriber)

**File:** `worker/worker/subscriber.py` → `TaskStreamSubscriber._run()`

`TaskStreamSubscriber` runs as a background `asyncio.Task` inside each worker process,
consuming from `stream:task` via a Redis Streams consumer group (`worker-group`). It bridges
the stream event into the in-process `EventBus`:

```python
event = TaskCreatedStreamEvent.from_payload(payload)
await self.event_bus.apublish(event)
await self.bus.ack(_STREAM, _GROUP, msg_id)  # always ack — even on handler error
```

The `TaskBiddingHandler` is bound to `TaskCreatedStreamEvent` on the in-process bus:

**File:** `worker/worker/handlers/bidding.py`

1. **Load agents**: all active agents in the workspace, with their current task executions
   pre-loaded (`selectinload`) to compute capacity.
2. **Score each agent**: `compute_bid_score()` — pure function, no I/O:
   - `skill_match` (0.60 weight): weighted coverage of `task.required_skills` by `agent.skills`
   - `capacity_factor` (0.20): how much headroom the agent has before hitting `max_parallel`
   - `influence_factor` (0.15): saturating exponential curve over `agent.influence`
   - `personality_fit` (0.05): cosine similarity between agent personality vector and task domain tags
   - Deterministic seeded jitter (±0.01 keyed on `task_id:agent_id`) breaks ties reproducibly
3. **Filter**: agents below `BID_SCORE_THRESHOLD` (default 0.3) are excluded.
4. **Reserve**: agents above threshold attempt `attempt_reservation()` in score order. This
   is an atomic Redis `SET NX EX` on key `reservation:{workspace_id}:{task_id}`. Exactly one
   agent gets `True` — the first to land the atomic write wins.
5. **Transition**: winner transitions task to `status="reserved"` and enqueues `execute_task`.

```
stream:task → TaskStreamSubscriber → EventBus → TaskBiddingHandler
  → compute_bid_score() × N agents
  → filter < threshold
  → attempt_reservation() — Redis SETNX — exactly one winner
  → Task(status="reserved") → DB
  → arq_queue.enqueue_job("execute_task", agent_id, task_id, workspace_id)
```

---

## Phase 2 — execute_task: read and guard

**File:** `worker/worker/jobs/execute_task.py`

ARQ picks up the job and invokes `execute_task()`. The function is structured as seven
phases, each with a deliberate session boundary.

### Phase 1 (READ)

Load `Agent` (with `selectinload(task_executions)` for capacity checks) and `Task` (with
`selectinload(subtasks)`). Session closes before any mutation. Objects become detached ORM
instances in Python memory.

Terminal-state guard: if ARQ retries a crashed job and the previous attempt already wrote
`status="completed"` or `"failed"`, return early. The state machine would reject the
transition anyway — this guard makes retries idempotent without relying on that.

### Phase 2 (WRITE EXECUTION ROW)

Create `TaskExecution(status="executing")` and transition task to `"executing"`. Commit
atomically. Creating the execution row early means a crashed process leaves a detectable
stale row in the DB — the sweeper can clean it.

`TaskActivityLogger.updated()` fires `TaskUpdatedEvent` on the in-process bus. This event
propagates to all registered handlers, but none act on the `executing` transition in Phase 1.

### Phase 3 (LLM EVALUATE)

One `llm_router.complete(CallType.EVALUATE)` call. The prompt receives agent context
(skills, influence) and task context (type, difficulty, required skills, delegation depth).
The model returns one of three decisions: `decompose`, `cfp`, or `self_execute`.

Depth guard: if `delegation_depth >= MAX_DELEGATION_DEPTH`, the decision is forced to
`self_execute` regardless of what the LLM returns. This prevents infinite delegation loops.

---

## Phase 3A — Decompose path

The agent decides the task is better broken into subtasks.

### Phase 4 (ACT — decompose)

1. A second LLM call (`CallType.DECOMPOSE`) generates subtask specs: title, description,
   task_type, required_skills, difficulty for each subtask.
2. `decompose_and_publish()` writes all subtask rows to Postgres with
   `parent_task_id = parent.id` and publishes `task.created` on Redis Streams for each.
   **The session is not committed inside this function** — the caller commits so all subtask
   rows and the parent status change land in one transaction. `session.flush()` assigns
   server-generated UUIDs before the bus publish so stream events carry real IDs.
3. `_finalise_execution()` closes the parent:
   - `execution.status = "completed"`, `execution_path = "decompose"`
   - `TaskStateMachine.transition(task, "completed")` — parent is done before any subtask runs
   - `task_logger.updated()` fires `TaskUpdatedEvent` with `execution_path="decompose"`

The `TaskUpdatedEvent` fires two handlers:
- `ReflectJobHandler`: SKIPS — guards on `execution_path != "self_execute"`
- `AgentCreditHandler`: runs `_credit_coordinator()` but finds no completed siblings yet →
  returns `[]` → no influence update yet. Credit is deferred to the last subtask.

`execute_task` returns. Each subtask is now in `status="open"` on `stream:task`, and each
goes through its own independent bidding cycle.

### Subtask completion and rollup

Each subtask goes through the full execute_task flow independently (possibly self-executing,
decomposing further, or issuing CFPs). When each subtask reaches a terminal state, it fires
`TaskUpdatedEvent`. Two handlers fire:

**`RollupSubtaskHandler`** (`worker/worker/handlers/rollup.py`):
1. Checks if all siblings have reached terminal status.
2. If not: returns. Another sibling is still running.
3. If yes (last sibling): transitions the parent... but the parent is already `"completed"`
   (set by `_finalise_execution`). The guard `parent.status in TERMINAL_STATUSES` returns
   early. Rollup skips the parent status transition.
4. Still queries for `avg_quality` across completed siblings and the parent's `decompose`
   execution ID.
5. Enqueues `reflect` for the coordinator agent with `execution_id` (decompose execution)
   and `quality_score` (avg sibling quality) — so the coordinator learns from how the
   decomposition went.

**`AgentCreditHandler`** (`worker/worker/handlers/agent_credit.py`):
1. `_credit_coordinator()` detects `parent_task_id is not None` → subtask path.
2. `_subtask_rollup_credits()`: waits until all siblings terminal, then computes avg quality
   and queries the parent task's delegation chain.
3. Decompose coordinator gets full `avg_quality` signal → `compute_influence_ema()`.
4. Writes `InfluenceSnapshot` for the coordinator.

```
Each subtask:
  → bidding → execute_task (self_execute or nested delegation)
  → completes → TaskUpdatedEvent fires:
      → RollupSubtaskHandler (on last sibling):
          → parent already completed — skips transition
          → queries avg sibling quality + decompose execution_id
          → enqueues reflect for coordinator
      → AgentCreditHandler (on last sibling):
          → _subtask_rollup_credits() → avg quality
          → EMA influence update for coordinator
```

---

## Phase 3B — CFP path

The agent decides it should not self-execute but wants to find the best agent via open
bidding.

### Phase 4 (ACT — cfp)

1. `issue_cfp()` publishes `cfp.issued` to `stream:cfp`. This broadcasts the task to all
   agents as a proposal request.
2. `_release_to_pool()`:
   - `execution.status = "completed"`, `execution_path = "cfp"`
   - `task.delegation_depth += 1` — depth guard incremented
   - `TaskStateMachine.transition(task, "open")` — task goes back to the pool, not completed
   - Redis reservation key deleted immediately — the TTL is no longer blocking
   - `stream_logger.task_created()` re-publishes `task.created` → standard bidding restarts
   - `task_logger.updated()` fires with `task.status = "open"` → `AgentCreditHandler` skips
     (status is not `"completed"`)

`execute_task` returns. The task is now back in the pool with one depth count consumed.

### CFP bidding and credit

The `CfpStreamSubscriber` runs on `stream:cfp` and fires `CfpIssuedStreamEvent` onto the
in-process bus. `CfpHandler` can apply CFP-specific bid logic (if wired) but the primary
re-entry is via the standard `task.created` event already re-published by `_release_to_pool`.

When the task is eventually won and self-executed, the completing agent fires
`TaskUpdatedEvent` with `execution_path = "self_execute"`. At that point:
- `AgentCreditHandler._credit_coordinator()` detects root task (no `parent_task_id`).
- Queries this task's delegation chain for `execution_path IN ("cfp", "decompose")`.
- CFP initiator gets `quality × CFP_COORDINATOR_CREDIT` (default 0.5) — partial credit for
  routing judgment.
- Executor gets full `quality` signal.

```
CFP initiator:
  → _release_to_pool() → task back to "open"
  → stream:cfp ← cfp.issued
  → stream:task ← task.created (re-bidding)

New agent wins → self-executes → completes:
  → AgentCreditHandler → credit CFP initiator (partial) + executor (full)
```

---

## Phase 3C — Self-execute path

The agent runs the task directly using a LangGraph ReAct loop.

### Phase 5 (SELF-EXECUTE via LangGraph)

No DB session is open during graph execution — connections are a scarce resource and graph
execution can take seconds.

`build_initial_state(agent, task)` constructs a `GraphState` with the agent's ID,
workspace ID, and a system message embedding both so tools know what to pass to memory
retrieval calls. Memory is **not** injected upfront — it is retrieved mid-execution via
tool calls when the agent decides it needs it.

The graph loops: `reason → call_tool → reason → ...` until the LLM produces a response
with no tool calls, or `step_count >= 10`. The `score_outcome()` function runs on the
final `GraphState`:

| Component | Weight | Measure |
|---|---|---|
| Artifact presence | 0.60 | 1.0 if `state["artifact"]` is set, else 0.1 |
| Step efficiency | 0.25 | Penalises runs near the 10-step limit |
| Tool engagement | 0.15 | Grows with tool count, neutral at 0 |

### Phase 6 (WRITE RESULTS — single atomic commit)

All writes for the self-execute path land in one session:

- `execution.status = "completed"`, `execution_path = "self_execute"`, `quality_score`,
  `artifact_uri`, `tool_trace`, `completed_at`
- **Skill decay**: `agent.skills = {k: max(0.0, v * (1 - SKILL_DECAY_RATE)) for all k}` —
  flat entropy decay applied once per task completion to prevent skill convergence. This is
  separate from the quality-weighted signal in `reflect`.
- `agent.updated_at`
- `TaskStateMachine.transition(task, "completed")`

`task_logger.updated()` fires `TaskUpdatedEvent` with `quality_score`, `execution_id`, and
`execution_path="self_execute"` on the in-process bus. **Four handlers fire:**

**`ReflectJobHandler`**: enqueues the `reflect` ARQ job with all five required parameters
(`agent_id`, `task_id`, `workspace_id`, `execution_id`, `quality_score`). Reflect runs
asynchronously — it is deliberately off the critical path.

**`AgentCreditHandler`**: `_credit_executor()` — applies EMA to the executor's influence:
`new = base + 0.15 * (quality - base)`. If quality < current influence, influence goes down.
Writes `InfluenceSnapshot`.

**`EpisodicMemoryHandler`**: writes an episode to Qdrant's `mem_episodic` collection for
this agent. The episode text encodes task type, domain tags, and quality score. Retrieved
semantically during future tasks to surface relevant past experience.

**`RollupSubtaskHandler`**: if the task has no `parent_task_id`, fires but returns early
(root task guard). If it is a subtask, runs sibling terminal check (see decompose flow above).

### Phase 7 (MEMORY + DOWNSTREAM EVENTS)

`stream_logger.task_completed()` publishes `task.completed` to Redis Streams (`stream:task`).
`TaskStreamSubscriber` bridges this to the in-process bus as `TaskCompletedStreamEvent`,
which fires **`SocialMemoryHandler`**:

- Queries all peer agents in the workspace (excluding the completing agent).
- Fans out `store_social()` writes to Qdrant's `mem_social` collection concurrently via
  `asyncio.gather`. Each peer receives an observation: *"Agent X completed a [task_type]
  task with quality score Y."*
- Per-peer failures are caught and logged — a single Qdrant error does not block the others.
- This is how agents build a model of each other's competence, informing delegation
  decisions in future CFP bids.

```
Phase 6 commit:
  ├── execution → completed
  ├── agent.skills *= (1 - SKILL_DECAY_RATE)   ← entropy decay
  └── task → completed

task_logger.updated() → in-process EventBus:
  ├── ReflectJobHandler      → enqueue reflect (async)
  ├── AgentCreditHandler     → EMA influence update + InfluenceSnapshot
  ├── EpisodicMemoryHandler  → Qdrant episodic write
  └── RollupSubtaskHandler   → sibling check (or root-task no-op)

stream_logger.task_completed() → Redis Streams → SocialMemoryHandler:
  └── peer social memory fan-out → Qdrant social writes × N peers
```

---

## Phase 4 — reflect job (async, self-execute and coordinator paths)

**File:** `worker/worker/jobs/reflect.py`

Runs after `execute_task` has committed. Loads `Agent`, `Task`, and `TaskExecution` fresh
from the DB — at this point `agent.skills` already carries Phase 6's decayed values.

**Complexity gate:**
```
full_reflect = task.difficulty >= 3.0 OR step_count > 3
```
Below threshold: skill deltas only (fast, cheap model). Above: skill deltas + generalised
rule extraction + supersession check against existing procedural rules.

**LLM call (`CallType.REFLECT`)**:
- Input: task metadata, result summary (`execution.artifact_uri`), tool trace,
  `quality_score`
- Output: `skill_deltas` (dict of skill → float in `[-0.2, +0.3]`), optionally
  `generalised_rule`, `verdict`, `superseded_ids`

**Skill delta application** — logistic growth (diminishing returns):
```
positive delta:  new = current + delta * (1 - current)   ← tapers toward 1.0
negative delta:  new = current + delta * current          ← tapers toward 0.0
```
An agent at 0.3 gains more absolute skill from a +0.2 delta than an agent at 0.8. An agent
at 0.1 loses less absolute skill from a -0.1 delta than an agent at 0.7. This prevents
saturation at the top and destruction at the bottom.

Applied deltas are merged into the agent's existing (already-decayed) skill dict:
`agent.skills = {**existing, **merged}`. Writes `SkillSnapshot` for observability.

For **full reflect** (above complexity gate):
- Existing procedural rules for the domain are retrieved from Qdrant.
- The LLM produces a `generalised_rule` and declares whether it supersedes, complements,
  or contradicts existing rules.
- `store_procedure()` writes to Qdrant with the verdict. Superseded rules are archived
  (`archived=True` in payload) and excluded from future retrievals.
- `ProceduralKnowledgeLog` row written to Postgres as a human-readable audit trail.

```
reflect(agent_id, task_id, workspace_id, execution_id, quality_score):
  → load Agent, Task, TaskExecution (fresh session — reads Phase 6 decayed skills)
  → full_reflect = difficulty >= 3 OR step_count > 3
  → LLM: task context + tool trace + quality → skill_deltas [, generalised_rule]
  → apply_skill_delta() × each delta → merged skills → SkillSnapshot
  → if full_reflect:
      → retrieve existing procedural rules from Qdrant
      → LLM: verdict (supersedes/complements/contradicts) + superseded_ids
      → store_procedure() → Qdrant (archived if superseded)
      → ProceduralKnowledgeLog → Postgres
```

---

## Phase 5 — Emergence metrics (concurrent cron)

**File:** `worker/worker/jobs/sample_metrics.py`
**Schedule:** every 15 seconds via ARQ cron

Runs independently of task execution. For each active workspace with ≥ 2 agents:

**Gini coefficient** over `agent.influence` scores:
- 0.0 = all agents equal influence (no emergent leadership)
- 1.0 = one agent holds all influence (single dominant coordinator)
- A healthy system stabilises somewhere between — clear leaders but genuine contribution
  from the broader pool.

**Specialisation index** — mean pairwise cosine distance between agent skill vectors:
- 0.0 = all agents have identical skill profiles (no specialisation)
- 1.0 = agents' skill vectors are completely orthogonal (perfect specialisation)
- Increasing index over time is the primary evidence that emergent differentiation is working.

**Hub detection**: any agent with `influence >= hub_influence_threshold` (from intelligence
config) triggers an `EmergenceEvent(event_type="hub_detected")` row.

All writes land in a single commit, then `workspace.metrics_update` is published to Redis
Streams so connected dashboards update in real time.

The metrics are computed from the current DB state. After Phase 6 commits (skill decay
applied) and before reflect completes (skill gains pending), the metrics reflect a
temporarily lower skill vector — a minor timing effect on a 15-second rolling window,
not a correctness issue.

---

## Complete flow diagram — self-execute path

```
Customer POST /tasks
  └─ API: validate → Task("pending") → enrich → Task("open") → stream:task ← task.created

Worker TaskStreamSubscriber
  └─ TaskBiddingHandler:
       compute_bid_score() × agents → SETNX reservation → Task("reserved")
       → arq_queue.enqueue_job("execute_task")

execute_task job
  Phase 1: READ              — Agent + Task loaded; session closes
  Phase 2: WRITE EXEC ROW    — TaskExecution("executing"), Task("executing")
  Phase 3: LLM EVALUATE      — decision: "self_execute"
  Phase 5: LANGGRAPH         — graph.ainvoke(); no open session
                               → tools may call store_episode, retrieve_episodes, etc.
  Phase 6: WRITE RESULTS     — execution + skills decay + agent.updated_at + Task("completed")
                               → task_logger.updated() fires:
                                    ReflectJobHandler    → enqueue reflect
                                    AgentCreditHandler   → EMA influence + InfluenceSnapshot
                                    EpisodicMemoryHandler → Qdrant episodic write
  Phase 7: DOWNSTREAM        — stream:task ← task.completed
                               → SocialMemoryHandler: peer social memory fan-out

reflect job (async)
  → load Agent (reads Phase 6 decayed skills)
  → LLM reflect → skill_deltas
  → apply_skill_delta() → SkillSnapshot
  → (if full_reflect) → generalised_rule → Qdrant procedural + ProceduralKnowledgeLog

sample_metrics cron (every 15s, concurrent)
  → Gini + specialisation_index + hub detection
  → WorkspaceMetricsSnapshot + EmergenceEvent
  → stream:workspace ← workspace.metrics_update
```

---

## Key invariants

**Skills and influence are never computed from scratch.** The DB row is the source of truth.
Python reads it, mutates it, writes it back. Every write is transactional. `sample_metrics`
reads whatever is committed; there is no cached or in-memory skill state.

**Skill decay and skill gains are separate mechanisms:**
- Decay (Phase 6): flat entropy, every task, all skills, no quality weighting
- Gains (reflect): LLM-targeted, quality-informed, logistic growth, only skills exercised

**Coordinator agents learn from influence, not skills.** Decompose and CFP coordinators
get no Phase 6 decay (they return before it) and no reflect gains from coordination actions
alone. Their competitive advantage comes from the influence factor in bid scoring. Skills
accumulate only when they self-execute.

**All four RL signals are quality-aware except decay:**
- Reflect deltas: `[-0.2, +0.3]` from LLM, scaled by logistic growth
- Influence EMA: `base + 0.15 * (quality - base)` → quality below base pulls influence down
- Social memory: peers receive observations including quality score for future delegation judgment
- Episodic memory: quality score stored with episode for future semantic retrieval

**No session held open during LangGraph execution.** Sessions are opened and closed per
phase. If a session stayed open across `graph.ainvoke()` the connection pool would starve
under load — graph execution takes seconds and the pool is finite.
