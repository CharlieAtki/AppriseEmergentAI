# Apprise — CLAUDE.md

## Project overview

Multi-tenant agent platform. Agents specialise through task execution. ContractNet bidding determines which agent handles each task. PostgreSQL is the source of truth; Python is a view of it.

**Stack:** FastAPI (`api`), ARQ worker (`worker`), shared library (`core`), PostgreSQL, Redis, Chroma/Qdrant, LangGraph, Clerk auth.

---

## The one rule that governs everything

> `api/` never runs agent logic. `worker/` never serves HTTP. `core/` never runs — it is a library.

Every structural question resolves from this. If you are writing an LLM call inside a router, or an HTTP request inside a job, stop.

---

## Separation of concerns

### Three processes, three responsibilities

| Process | Does | Never |
|---|---|---|
| `api/` | validate, store, enqueue, query | LLM calls, LangGraph, agent decisions |
| `worker/` | LLM calls, graph execution, scoring, memory writes | serve HTTP, business-level validation |
| `core/` | shared models, coordination, bus, events, activity loggers, intelligence, memory | own an entrypoint or run directly |

### Where does X belong?

- Both `api/` and `worker/` need it → `core/`
- Only ever invoked by an ARQ job → `worker/jobs/`
- Pure logic with no dependency on ARQ, HTTP, or Redis Streams → `core/`
- Serving, validating, or querying data for a customer → `api/`

### Intelligence layer — six files, six jobs

Each file in `core/intelligence/` has exactly one responsibility. Do not expand these:

| File | Single job |
|---|---|
| `registry.py` | In-memory model catalog. Stores `ModelEntry` dicts. Nothing else. |
| `sync.py` | Reconciles registry → DB at startup. Never called at request time. |
| `routing_config.py` | Merges platform defaults + workspace overrides into a routing table. |
| `llm_router.py` | Dispatches LLM calls. Resolves model, builds client, applies semaphore. |
| `call_types.py` | Enum of call types. No logic. |
| `prompts/` | One file per call type. Returns a prompt string. No dispatch, no parsing of responses beyond its own type. |

---

## KISS — Keep It Simple

### Pure functions for pure logic

Bid scoring, skill matching, capacity factors, influence transforms — these are pure functions. They take values and return values. No I/O, no async, no DB reads.

```python
# correct — pure function, all state passed in by the caller
def compute_bid_score(agent_skills, agent_influence, ...) -> float: ...

# wrong — hidden I/O inside what looks like a calculation
async def compute_bid_score(agent_id, task_id, session) -> float: ...
```

The caller (worker job) is responsible for loading state. The function is responsible for the math.

### No LLM in the coordination layer

`core/coordination/` is deterministic. `compute_bid_score`, `attempt_reservation`, `TaskStateMachine` — none of these call an LLM or read the database. Bid scoring uses only values the caller passes in.

### No preprocessing — memory retrieval is a tool call

Agents retrieve episodic, procedural, and social memory mid-execution via tool calls. It is not injected upfront. This is what makes a specialist different from an agent with good context.

---

## Decoupling

### Interfaces over concrete types

The bus is typed against `BusProtocol`, not `RedisBus`. The worker uses `SubscribableBusProtocol`. Tests swap in `InMemoryBus`. No concrete bus class bleeds into coordination or job logic.

```python
# correct — decoupled from transport
async def decompose_and_publish(agent, parent_task, subtask_specs, session, bus: BusProtocol): ...

# wrong — coupled to Redis
async def decompose_and_publish(..., redis: Redis): ...
```

Vendor implementations satisfy `VendorProvider` ABC. `LLMRouter` works against the ABC, not any specific vendor SDK.

### Self-registration over central wiring

Importing a vendor package is the act of registering it. `core/vendors/anthropic/__init__.py` calls `registry.add_model(...)` as a module-level side effect. There is no central list of vendors.

```python
# core/vendors/anthropic/__init__.py — registration is the import
registry.add_model("anthropic/claude-haiku-4-5-20251001", vendor="anthropic", ...)
```

Adding a vendor: create the package and add one import line to the lifespan hook. That is the complete change.

### TYPE_CHECKING for circular avoidance

Use `TYPE_CHECKING` guards for imports that would create circular dependencies. The import only runs for the type checker, not at runtime.

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.models.tasks import Task
```

### Workspace-scoped Redis keys

Every Redis key that varies by workspace must include `workspace_id`. The reservation lock key is the most critical:

```python
f"reservation:{workspace_id}:{task_id}"   # correct
f"reservation:{task_id}"                   # wrong — cross-workspace collision
```

---

## Event bus

### The two buses

| Bus | Class | Transport | Use |
|-----|-------|-----------|-----|
| In-process | `EventBus` | asyncio | Same-process side effects: audit logging, cache invalidation, metrics |
| Cross-process | `RedisBus` | Redis Streams | Durable task coordination events (`task.created`, `task.completed`) |

`EventBus` does not survive process restart and never should — it is for side effects the current process cares about. `RedisBus` is for events that must reach other processes or survive crashes. Never conflate them.

### Producers never touch the bus directly

Domain code never calls `bus.apublish()` directly. The only legitimate way to publish an event is through an activity logger:

```python
# correct — logger is the only producer interface
await logger.created(task)

# wrong — domain code coupling to the event model
await bus.apublish(TaskCreatedEvent(state=TaskSnapshot.from_domain(task), workspace_id=task.workspace_id))
```

The logger facade's only job is to construct the right event from a SQLAlchemy model and hand it to a `PublishFn` callable. It knows nothing about handlers, dispatch, or who is listening.

### One activity logger per domain area

```
core/activity/task_logger.py    ← TaskActivityLogger
core/activity/agent_logger.py   ← AgentActivityLogger
```

Loggers receive `PublishFn = Callable[[DomainEvent], Awaitable[None]]` at construction — never the bus directly. This is the smallest possible surface area and makes them trivial to test with `AsyncMock()`.

```python
# correct — standalone logger, holds publish callable
class TaskActivityLogger:
    def __init__(self, publish: PublishFn) -> None: ...

# wrong — logger holds the bus
class TaskActivityLogger:
    def __init__(self, bus: EventBus) -> None: ...
```

Method names describe the domain action, not generic CRUD. The class name already scopes the entity:

```python
await logger.created(task)          # not logger.task_created(task)
await logger.updated(before, task)  # not logger.task_updated(before, task)
await logger.deleted(task)          # not logger.task_deleted(task)
```

### Snapshots must be taken before the session closes

`XSnapshot.from_domain(orm_model)` reads already-loaded scalar attributes by name. It does not trigger lazy loads. Call it while the ORM object is still attached to an open session and before you mutate it:

```python
# correct — before snapshot captured before mutation; logger snapshots after internally
before = TaskSnapshot.from_domain(task)
task.status = "in_progress"
await logger.updated(before, task)

# wrong — snapshot taken after mutation; before and after read the same mutated state
task.status = "in_progress"
before = TaskSnapshot.from_domain(task)   # too late — already mutated
await logger.updated(before, task)
```

`from_domain` also handles nested snapshots (`SnapshotSubclass | None` fields) and snapshot collections (`tuple[SnapshotSubclass, ...]`) via type-hint introspection. Override it on the concrete class when field names diverge or values need transformation.

### Events live in `core/events/`, import nothing from the domain

```
core/events/task_events.py    ← TaskSnapshot, TaskCreatedEvent, TaskUpdatedEvent, TaskDeletedEvent
core/events/agent_events.py   ← AgentSnapshot, AgentCreatedEvent, AgentUpdatedEvent, AgentDeletedEvent
```

Event files import only from `core/bus/common.py` and stdlib. No ORM imports, no bus imports, no activity logger imports. This is what keeps the event model dependency-free and importable in isolation.

### Handler registration and composition

All handlers run fire-and-forget. Compose behaviour at the registration site using the wrappers in `core/bus/handlers.py`:

```python
# basic fire-and-forget
bus.bind(TaskCreatedEvent, AuditLogHandler())

# bind one handler to multiple event types
bus.bind([TaskCreatedEvent, AgentCreatedEvent], MetricsHandler())

# retry on transient failures
bus.bind(AgentDeletedEvent, Retry(CleanupHandler(), retry_on=(OperationalError,)))

# sync handler wrapped for async dispatch
bus.bind(AgentDeletedEvent, SyncToAsync(ComplianceHandler()))

# predicate gate — handler only runs when condition is true
bus.bind(TaskCreatedEvent, Filtering(AuditLogHandler(), predicate=lambda e: e.state.workspace_id == REGULATED_WS))
```

Handlers are registered once at startup — never at request time.

### Wiring

**FastAPI** — bus lives on `app.state.bus`; dep factories in `api/deps.py` inject `apublish` into loggers at request time:

```python
def get_event_publisher(bus: EventBus = Depends(get_bus)) -> PublishFn:
    return bus.apublish

def get_task_activity_logger(publish: PublishFn = Depends(get_event_publisher)) -> TaskActivityLogger:
    return TaskActivityLogger(publish)
```

**Worker** — construct loggers directly from `WorkerContext`:

```python
logger = TaskActivityLogger(wctx.bus.apublish)
```

Call `await bus.drain_pending()` in both FastAPI and ARQ shutdown hooks to drain in-flight fire-and-forget tasks before the process exits.

### Single responsibility in the event layer

- `TaskActivityLogger` only constructs and publishes task events — no DB access, no handler logic
- `EventHandler` implementations only handle — they do not publish back onto the bus
- Snapshots only capture state — `from_domain` reads attributes and nothing else
- `EventBus` only dispatches — it does not know what events mean or what to do with them

---

## Single responsibility per class and function

### `ModelRegistry` only registers

`ModelRegistry` maps `model_id → ModelEntry`. It does not build models. It does not read from the database. It does not know what a `VendorProvider` is.

### `sync_models()` only syncs

`sync_models()` reconciles the in-memory registry against the `models` Postgres table. It runs once at startup. It is never called at request time.

### `resolve_routing()` only merges configs

`resolve_routing()` takes platform defaults and workspace overrides and returns a merged routing table. It does not dispatch anything.

### `LLMRouter` only dispatches

`LLMRouter` resolves a model from the routing table, builds it via the vendor provider (cached after first call), and invokes it. It does not register models. It does not know which models exist globally — only what the catalog and routing table say.

### `TaskStateMachine` only guards transitions

`TaskStateMachine.transition()` validates the status change and applies it. It does not load from the database, publish events, or update related records. The caller does those.

### `decompose_and_publish()` only persists and publishes

The caller (worker job) generates `subtask_specs` — either via LLM or heuristic. `decompose_and_publish()` only writes subtasks to Postgres and publishes events. It does not call the LLM. The session is not committed here; the caller commits so all writes land in one transaction.

### Routers are thin

API routers validate input and call a service function or write to the database. Business logic does not live in routers. If you are writing conditional agent logic in a router, it belongs in the worker.

---

## Specific hard rules

### Jobs, not asyncio tasks

```python
# wrong — dies with the process
asyncio.create_task(execute_task(agent_id, task_id))

# correct — survives crash, retried automatically
await queue.enqueue_job("execute_task", agent_id=agent_id, task_id=task_id, workspace_id=workspace_id)
```

### LLM calls only in the worker

All LLM calls for agent reasoning go through `LLMRouter` and are invoked from `worker/jobs/` only. The API may make a single lightweight LLM call for task enrichment, isolated in its own path. Never add LLM calls to routers or middleware.

### registry.py must stay dependency-free

`core/intelligence/registry.py` has no DB import, no vendor SDK, no credentials, no settings import. It cannot fail to import. Protect this invariant — any circular import between the registry and a vendor package causes silent registration failure.

### Chroma always uses the HTTP client

```python
# correct
client = chromadb.HttpClient(url="http://chroma:8001")

# wrong — creates a local directory, silently puts memories in the wrong place
client = chromadb.Client()
```

### Alembic for every schema change

Every change to a `core/models/` class that affects the database schema needs a migration file committed in the same PR. Generate with:
```bash
cd core && alembic revision --autogenerate -m "describe the change"
```
Never run `ALTER TABLE` directly.

### Config changes touch both files

`config.py` defaults apply everywhere `.env` is absent. `.env` wins at runtime. Update both in the same commit. A gap between them silently breaks CI and fresh clones.

### LangGraph graphs compile at worker startup

Graph compilation is expensive. Compile in the ARQ `startup()` hook and reuse across all jobs in the process. Never compile inside a job function.

---

## Comments

Default to writing no comments. Add one only when the **why** is non-obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug, behaviour that would surprise a reader.

Do not explain what the code does. Well-named identifiers do that. Do not reference the current task, ticket, or caller — those belong in the PR description and rot as the codebase evolves.

---

## Development notes

- Ollama must run natively on the host OS, not inside Docker. Docker on Mac/Windows has no access to Metal/CUDA GPU. For development without a local GPU, use `LLM_BACKEND=anthropic`.
- Auth middleware maps Clerk claims (`clerk_user_id`, `clerk_org_id`) → internal UUIDs. Downstream code trusts `request.state.org_id` and never re-validates Clerk tokens.
- The `models` table is written only by `sync_models()` at startup. Never write to it at request time.
- Workspace routing config (`workspace_model_routing`) is the only place per-workspace model preferences live. Never embed workspace preferences in the registry.
