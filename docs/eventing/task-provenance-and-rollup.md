# Task Provenance, Delegation Depth, and Subtask Rollup

## Why this exists

When an agent decomposes a task into subtasks, three things were missing:

1. **No record of who is responsible.** The subtasks had a `parent_task_id` but nothing said *which agent* coordinated the decomposition or *who created* each subtask. There was no way to credit the coordinator when all subtasks completed successfully.

2. **No loop guard.** An agent could decompose a task. Each subtask could also choose to decompose. This could continue indefinitely. Nothing in the system prevented it.

3. **No completion rollup.** When the last subtask finished, nothing happened to the parent task. It sat in `"executing"` forever. A human or another job would have had to clean it up.

This document explains the three mechanisms added to solve these problems:

- `TaskContext` — a frozen dataclass that carries provenance in-process
- Provenance columns on `Task` — persistence that survives process restarts and bus hops
- `RollupSubtaskHandler` — an in-process event handler that closes the loop

---

## The data model: three new columns on `Task`

```sql
coordinator_agent_id  UUID  NULL  REFERENCES agents(id) ON DELETE SET NULL
created_by_agent_id   UUID  NULL  REFERENCES agents(id) ON DELETE SET NULL
delegation_depth      INT   NOT NULL  DEFAULT 0
```

### `coordinator_agent_id`

The agent that will receive credit when this task's subtree completes. Set once at decomposition time and never changed. For a root task created directly by a user (through the API), this is `NULL`.

When an agent A decomposes task T into subtasks S1, S2, S3:
- Each subtask gets `coordinator_agent_id = A.id` (or A's own coordinator if A is already a subtask coordinator — more on this below)

When all of S1, S2, S3 reach a terminal state, the `RollupSubtaskHandler` credits agent A by updating its `influence` score. This means the coordinator benefits from good delegation, not just from direct execution.

### `created_by_agent_id`

The agent that directly created this task. For subtasks, this is always the decomposing agent. For root tasks, `NULL`. This is distinct from `coordinator_agent_id`: an agent can coordinate a task it did not create (e.g. a coordinator issues a CFP, a different agent wins and creates sub-subtasks — the original coordinator still coordinates, but the sub-subtasks were created by the winner).

### `delegation_depth`

An integer starting at `0` for root tasks. Every time `decompose_and_publish` creates subtasks, each subtask gets `parent.delegation_depth + 1`. This prevents infinite delegation loops:

```
Root task          depth=0
  └─ Subtask A     depth=1
       └─ Sub-A1   depth=2
            └─ ... depth=3
```

`MAX_DELEGATION_DEPTH = 5` is defined in `core/coordination/task_context.py`. When a task reaches or exceeds this depth, the worker job overrides the LLM's decision and forces `self_execute`. The LLM is also told about this constraint in its prompt so it is less likely to choose decompose near the limit.

---

## `TaskContext` — in-process provenance carrier

```python
# core/coordination/task_context.py

@dataclass(frozen=True)
class TaskContext:
    task_id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    parent_task_id: uuid.UUID | None
    coordinator_agent_id: uuid.UUID | None
    created_by_agent_id: uuid.UUID | None
    delegation_depth: int

    @classmethod
    def from_task(cls, task: Task) -> TaskContext: ...
```

### Why a separate dataclass?

`Task` is a SQLAlchemy ORM object. It is bound to a session, can trigger lazy loads, and is not safe to hold across `async with session` boundaries. Coordination functions (`decompose_and_publish`, the depth guard) only need the lineage data, not the full ORM model.

`TaskContext` is a frozen dataclass with no I/O, no session, no async. It is:
- **Constructed once** in Phase 1 of `execute_task`, while the task is loaded and the session is still open
- **Passed down** to any function that needs lineage data
- **Testable in isolation** — tests can construct a `TaskContext` directly without touching a database

```python
# In execute_task.py — Phase 1

async with span.session() as session:
    task = await session.get(Task, uuid.UUID(task_id), ...)
    # session is still open here

# Build provenance while scalar attributes are still in-memory.
# expire_on_commit=False on SessionLocal keeps them after session close.
provenance = TaskContext.from_task(task)
depth_exceeded = provenance.delegation_depth >= MAX_DELEGATION_DEPTH
```

`from_task` only reads scalar attributes (`task.id`, `task.workspace_id`, etc.) — it does not traverse relationships. This is safe on a detached SQLAlchemy instance because `expire_on_commit=False` is set on the session factory, which means scalar values stay in `instance.__dict__` after the session closes.

### Why not use Python `contextvars`?

`contextvars` are per-asyncio-task, in-process only. The moment `execute_task` enqueues a subtask as an ARQ job (`arq_queue.enqueue_job(...)`), the context crosses a process boundary via Redis. `contextvars` cannot survive that hop. The data has to be serialised into the task row itself — which is exactly what the three columns do. `TaskContext` is then just a convenient typed handle over that persisted data.

---

## How provenance flows through the system

### Happy path: agent decomposes

```
execute_task(agent=A, task=T)
    Phase 1: provenance = TaskContext.from_task(T)
             provenance.delegation_depth = 0
             provenance.coordinator_agent_id = None  (root task)

    Phase 4 (decompose):
        decompose_and_publish(
            agent=A, parent_task=T, specs=[...],
            task_ctx=provenance, task_logger=task_logger
        )
        → for each subtask S:
              S.coordinator_agent_id = provenance.coordinator_agent_id or A.id
              #                       = None or A.id
              #                       = A.id
              S.created_by_agent_id  = A.id
              S.delegation_depth     = 0 + 1 = 1

    ARQ enqueues execute_task(agent=B, task=S1)
    ARQ enqueues execute_task(agent=C, task=S2)
```

Now S1 and S2 both carry `coordinator_agent_id = A.id` and `delegation_depth = 1`.

When agent B executes S1:
```
execute_task(agent=B, task=S1)
    Phase 1: provenance.coordinator_agent_id = A.id
             provenance.delegation_depth = 1

    Phase 6 (completed):
        task_logger.updated(before_completed, task)
        → fires TaskUpdatedEvent on wctx.event_bus
        → RollupSubtaskHandler.handle(event)
            event.state.parent_task_id = T.id  ← has a parent
            event.state.status = "completed"   ← terminal
            queries siblings: [S1=completed, S2=still executing]
            not all terminal → returns
```

When agent C completes S2:
```
execute_task(agent=C, task=S2)
    Phase 6 (completed):
        task_logger.updated(before_completed, task)
        → TaskUpdatedEvent fired
        → RollupSubtaskHandler.handle(event)
            queries siblings: [S1=completed, S2=completed]
            all terminal → proceeds
            loads parent T
            T.status = "executing" → not terminal → transitions to "completed"
            all_succeeded → _credit_coordinator(session, T, [S1, S2])
                loads agent A
                avg_quality = avg(S1.execution.quality_score, S2.execution.quality_score)
                A.influence = EMA(A.influence, avg_quality)
                writes InfluenceSnapshot
            enqueues reflect(agent_id=A.id, task_id=T.id)
```

### Nested decomposition: coordinator inheritance

If agent B (executing S1) also decides to decompose S1 into sub-subtasks:

```
execute_task(agent=B, task=S1)
    provenance.coordinator_agent_id = A.id   ← inherited from S1
    provenance.delegation_depth = 1

    Phase 4 (decompose):
        decompose_and_publish(task_ctx=provenance, ...)
        → for each sub-subtask SS:
              SS.coordinator_agent_id = A.id or B.id
              #                       = A.id  ← A is non-None, so A stays coordinator
              SS.created_by_agent_id  = B.id
              SS.delegation_depth     = 2
```

The original coordinator (A) stays the coordinator all the way down the tree. The expression `task_ctx.coordinator_agent_id or agent.id` ensures that once a coordinator is set, it propagates unchanged. Only the root decomposition (where `coordinator_agent_id` is `None`) sets the coordinator to the decomposing agent.

### CFP path: coordinator preserved

When an agent issues a CFP (delegates to a better-suited agent via ContractNet bidding), the `coordinator_agent_id` from the task is carried into the CFP payload:

```python
# coordination/contract_net.py
await bus.publish(
    f"cfp.{task.workspace_id}.issued",
    {
        ...
        "coordinator_agent_id": str(task.coordinator_agent_id) if task.coordinator_agent_id else None,
        ...
    }
)
```

When the task is re-released to the bidding pool via `_release_to_pool`, the task row already has the `coordinator_agent_id` column set, so the next agent that picks it up inherits the full provenance correctly.

---

## The delegation depth guard

Two layers of protection against infinite decomposition:

### Layer 1: LLM prompt instruction

`evaluate.py` now includes `delegation_depth` and `depth_exceeded` in the prompt:

```
Delegation depth: 3
Depth exceeded: False
```

And in the system instruction:
```
If depth_exceeded is true, you MUST choose self_execute regardless of other factors.
```

The LLM sees how deep it already is and is instructed not to decompose further when the limit is reached.

### Layer 2: Hard override in the job

Even if the LLM ignores the instruction (hallucination, prompt injection, etc.), the job enforces it:

```python
# execute_task.py — Phase 3

decision = evaluate.parse(raw)

if depth_exceeded and decision.decision != "self_execute":
    logger.warning(
        "execute_task: depth guard forcing self_execute for task=%s (depth=%d)",
        task.id, provenance.delegation_depth,
    )
    decision = EvaluateResponse(decision="self_execute", reasoning="depth guard")
```

`depth_exceeded` is a boolean computed once: `provenance.delegation_depth >= MAX_DELEGATION_DEPTH`. The override happens before Phase 4, so the decompose and CFP code paths are never reached for tasks at or beyond the depth limit. The task is always self-executed, no matter what the LLM said.

---

## The event bus integration: how `task_logger` connects to rollup

This is the piece that ties everything together. Understanding it requires knowing how the two buses work together.

### Two buses, two purposes

| Bus | Variable | Transport | Purpose |
|-----|----------|-----------|---------|
| In-process `EventBus` | `wctx.event_bus` | asyncio | Same-process side effects: rollup, audit, metrics |
| `RedisBus` | `wctx.bus` | Redis Streams | Cross-process durable coordination |

The `RollupSubtaskHandler` runs on the **in-process** `EventBus`. It does not need to cross process boundaries — when a subtask completes inside `execute_task`, the rollup check and potential parent completion happen in the same worker process, fire-and-forget.

### `task_logger` — the bridge

```python
# execute_task.py

task_logger = TaskActivityLogger(wctx.event_bus.apublish)
```

`TaskActivityLogger` is a thin facade. Its only job is to construct a correctly shaped `TaskUpdatedEvent` from a SQLAlchemy model and forward it to a `PublishFn` callable. It knows nothing about the bus, handlers, or what happens next.

`wctx.event_bus.apublish` is that callable — it schedules all registered handlers fire-and-forget.

The `RollupSubtaskHandler` is registered against `TaskUpdatedEvent` at worker startup:

```python
# worker/startup.py

wctx.event_bus.bind(TaskUpdatedEvent, RollupSubtaskHandler(arq_queue=wctx.arq_queue))
```

So the chain is:

```
task_logger.updated(before, task)
    → constructs TaskUpdatedEvent(state=after_snapshot, before=before_snapshot)
    → calls wctx.event_bus.apublish(event)
        → schedules RollupSubtaskHandler.handle(event) as asyncio.Task (fire-and-forget)
        → execute_task continues immediately — it does not wait for rollup
```

### Where `task_logger.updated()` is called in `execute_task`

`updated()` is called after **every DB commit that changes task status**. The `before` snapshot must be captured *before* the ORM mutation, while the task's current status is still the old one:

| Phase | Before captured when | Status transition | Logger call after |
|-------|----------------------|-------------------|-------------------|
| 2 | Before session block | `reserved → executing` | `await task_logger.updated(before_executing, task)` |
| 4 (decompose) | Inside `_finalise_execution` | `executing → completed` | Inside helper |
| 4 (CFP) | Inside `_release_to_pool` | `executing → open` | Inside helper |
| 6 (self-execute) | Before session block | `executing → completed` | `await task_logger.updated(before_completed, task)` |
| Error path | Before failure transition | `executing → failed` | `await task_logger.updated(before_failed, task)` |

The `before` snapshot is what lets `TaskUpdatedEvent.changed("status")` work correctly:

```python
event.before.status   # "executing"
event.state.status    # "completed"
event.changed("status")  # True
```

If we captured `before` after the mutation, both would read `"completed"` and `changed()` would return `False` — the rollup handler would silently do nothing.

### Why fire-and-forget is correct here

`task_logger.updated()` schedules the rollup handler as a background asyncio task. `execute_task` does not `await` the handler's completion before moving to Phase 7 (memory write, Redis publish, reflect enqueue).

This is intentional:
- The rollup only reads the sibling statuses from the DB. It does not need the Phase 7 Redis event to have been published first.
- Phase 7 takes time (Qdrant write, Redis publish, ARQ enqueue). Making rollup wait for Phase 7 would add latency with no benefit.
- If the rollup handler fails (DB error, network blip), it is caught and logged. The `_safe_handle` wrapper in `EventBus` ensures a failing handler never affects the publishing job.

The only risk is: what if the worker process dies between Phase 6 commit and the rollup handler completing? The rollup handler is in-process — it does not survive crashes. The mitigation is `drain_pending()` in the shutdown hook:

```python
# worker/startup.py — shutdown

await wctx.event_bus.drain_pending()   # await all in-flight handlers
await wctx.bus.close()
await wctx.redis.aclose()
```

On graceful shutdown (SIGTERM), `drain_pending()` waits for all in-flight asyncio tasks before the process exits. On a hard crash (SIGKILL, OOM), in-flight handlers are lost. This is an accepted trade-off: a hard crash is rare, and the parent task can be recovered manually or by a future housekeeping job.

---

## `RollupSubtaskHandler` — detailed walkthrough

```python
# worker/handlers/rollup.py

TERMINAL_STATUSES = frozenset({"completed", "failed", "expired"})

@dataclass
class RollupSubtaskHandler(EventHandler[TaskUpdatedEvent]):
    arq_queue: ArqRedis
```

It holds `arq_queue` because completing a parent task triggers a `reflect` job for the coordinator agent.

### `handle()` — early exits

```python
async def handle(self, event: TaskUpdatedEvent) -> None:
    if not event.changed("status"):
        return
```

`TaskUpdatedEvent` fires on any task update, not just status changes. An update to `title`, `description`, or any other field would also fire this event. The first guard ensures the handler only does real work when the status actually changed. Without this, every task edit would trigger a sibling query.

```python
    if event.state.status not in TERMINAL_STATUSES:
        return
```

Only terminal statuses trigger rollup. If the task just moved to `"executing"`, there is nothing to roll up yet.

```python
    if event.state.parent_task_id is None:
        return
```

Root tasks have no parent. No rollup needed.

### `_evaluate_parent()` — the sibling check

```python
siblings = (await session.execute(
    select(Task).where(
        Task.parent_task_id == parent_id,
        Task.workspace_id == workspace_id,
    )
)).scalars().all()
```

Both `parent_task_id` and `workspace_id` are in the filter. `workspace_id` is technically redundant (UUID uniqueness prevents cross-workspace collisions) but follows the CLAUDE.md invariant: all workspace-scoped queries must include `workspace_id`. It also makes the query use the composite index `ix_tasks_workspace_id_status_created_at` if the planner prefers it.

```python
if not {s.status for s in siblings}.issubset(TERMINAL_STATUSES):
    return
```

If any sibling is still `"executing"`, `"pending"`, `"open"`, `"reserved"`, or `"enriching"`, the set will not be a subset of terminal statuses and the handler returns early. The handler that fires for the *last* completing sibling will be the one that proceeds past this check.

### The concurrent rollup race condition

Two subtasks, S1 and S2, both complete within milliseconds of each other. Two instances of `RollupSubtaskHandler.handle()` are scheduled:

```
Handler for S1 completion:
    queries siblings → [S1=completed, S2=completed]
    all terminal → proceeds
    loads parent T → T.status = "executing"
    transitions T → "completed"
    commits

Handler for S2 completion (running slightly after):
    queries siblings → [S1=completed, S2=completed]
    all terminal → proceeds
    loads parent T → T.status = "completed"
    T.status in TERMINAL_STATUSES → returns immediately  ← guard fires
```

The guard is:

```python
parent = await session.get(Task, parent_id)
if parent is None or parent.status in TERMINAL_STATUSES:
    return
```

Because `get_session()` uses `expire_on_commit=False` and a fresh session per handler call, the second handler sees the committed state written by the first. The `TaskStateMachine.transition()` call would also raise `InvalidTaskTransition` if somehow both handlers loaded the same status, providing a second layer of protection.

### Partial failure

```python
any_failed = any(s.status == "failed" for s in siblings)
target_status = "failed" if any_failed else "completed"
TaskStateMachine.transition(parent, target_status)
```

If even one sibling failed, the parent fails. No coordinator credit is written (partial failure means the coordination was not successful). The `reflect` job is still enqueued — the coordinator needs to learn from delegation failure as much as from success.

### Credit rollup

```python
async def _credit_coordinator(self, session, parent, siblings):
    completed_ids = [s.id for s in siblings if s.status == "completed"]
    avg_quality = (await session.execute(
        select(func.avg(TaskExecution.quality_score)).where(
            TaskExecution.task_id.in_(completed_ids),
            TaskExecution.status == "completed",
        )
    )).scalar() or 0.0

    base = coordinator.influence or 0.0
    coordinator.influence = base + settings.INFLUENCE_EMA_ALPHA * (avg_quality - base)
```

`quality_score` comes from `TaskExecution` rows written by the executing agents in Phase 6 of their respective `execute_task` jobs. Only `status == "completed"` executions are included — failed executions have no meaningful quality score and would drag down the average unfairly.

The EMA (Exponential Moving Average) blends the new quality signal into the coordinator's running influence. The same formula is used for direct execution in `execute_task._update_influence()`. The coordinator's influence thus reflects both their direct task performance and the quality of the teams they assembled.

An `InfluenceSnapshot` is also written. These are time-series records used to track influence over time — the same pattern as the `SkillSnapshot` written in Phase 6.

---

## Startup and shutdown

### Registration at startup

```python
# worker/startup.py

wctx.event_bus.bind(TaskUpdatedEvent, RollupSubtaskHandler(arq_queue=wctx.arq_queue))
```

Handlers are registered once at startup. The `EventBus.bind()` call is inside a local import block to avoid circular import risk at module load time (`worker.handlers.rollup` imports from `core.database`, `core.models`, etc.).

`RollupSubtaskHandler` receives `arq_queue` at construction time because it needs to enqueue the reflect job. This is constructor injection — the handler does not read from any global context.

### Drain at shutdown

```python
# worker/startup.py — shutdown hook

await wctx.event_bus.drain_pending()   # must come FIRST
await wctx.bus.close()
await wctx.redis.aclose()
```

`drain_pending()` awaits all in-flight asyncio tasks. It must run before closing Redis connections because in-flight rollup handlers may be mid-way through `_credit_coordinator`, which queries the DB and enqueues a job via `arq_queue` (which uses the ARQ Redis connection). Closing Redis before draining would cause those handlers to fail with connection errors.

---

## FastAPI side

`api/api/main.py` creates an `EventBus` in the FastAPI lifespan and attaches it to `app.state.bus`. This is what `api/deps.py` reads:

```python
def get_bus(request: Request) -> EventBus:
    return request.app.state.bus
```

The API-side EventBus has no handlers registered (yet). The API never completes tasks, so `RollupSubtaskHandler` is not needed there. When audit log handlers or cache invalidation handlers are added, they will be registered in the lifespan's handler registration block.

The API bus and the worker bus are **separate instances**. They do not share state. An event published on the API bus is not seen by the worker bus and vice versa. This is intentional — cross-process coordination goes through Redis Streams, not the in-process bus.

---

## Adding a new handler that cares about task completion

If you want to add a new side effect that runs when a task completes (e.g. send a webhook, write to an audit log), you do **not** modify `execute_task.py` or `RollupSubtaskHandler`. Instead:

1. Create a new `EventHandler[TaskUpdatedEvent]` subclass:

```python
class WebhookDispatchHandler(EventHandler[TaskUpdatedEvent]):
    async def handle(self, event: TaskUpdatedEvent) -> None:
        if not event.changed("status") or event.state.status != "completed":
            return
        # dispatch webhook ...
```

2. Register it at startup:

```python
# worker/startup.py
wctx.event_bus.bind(TaskUpdatedEvent, WebhookDispatchHandler(...))
```

Both handlers receive the same `TaskUpdatedEvent`. The `EventBus` walks its handler list and schedules all of them fire-and-forget. They run concurrently. A failure in one does not affect the other.

---

## Summary: the complete call chain for a subtask completing

```
execute_task (worker process, Phase 6)
    DB commit: task.status = "completed"
    await task_logger.updated(before_completed, task)
        → TaskActivityLogger constructs TaskUpdatedEvent
        → wctx.event_bus.apublish(event)
            → asyncio.ensure_future(RollupSubtaskHandler.handle(event))
            → execute_task continues to Phase 7 immediately

Phase 7 (concurrent with rollup handler):
    wctx.memory.store_episode(...)        → Qdrant write
    wctx.bus.publish("stream:task", ...)  → Redis Streams → subscriber → social memory
    arq_queue.enqueue_job("reflect", ...) → ARQ job for the executing agent

RollupSubtaskHandler.handle(event) [fire-and-forget asyncio task]:
    event.changed("status") → True
    event.state.status = "completed" → in TERMINAL_STATUSES
    event.state.parent_task_id = T.id → not None
    async with get_session():
        query siblings of T → all terminal
        load parent T → status "executing" → not terminal
        transition T → "completed"
        _credit_coordinator:
            load coordinator agent A
            avg quality across completed siblings
            EMA → A.influence updated
            write InfluenceSnapshot
        commit
        enqueue reflect(agent_id=A.id, task_id=T.id)
```

The parent task is completed, the coordinator is credited, and a reflect job is enqueued — all without a single line of code added to `execute_task.py`'s core logic. The job just fires an event and moves on.
