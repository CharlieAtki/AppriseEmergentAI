# Apprise — CLAUDE.md

## Project overview

Multi-tenant agent platform. Agents specialise through task execution. ContractNet bidding determines which agent handles each task. PostgreSQL is the source of truth; Python is a view of it.

**Stack:** FastAPI (`api`), ARQ worker (`worker`), shared library (`core`), PostgreSQL, Redis, Chroma/Qdrant, LangGraph, Clerk auth.

---

## Design Context

Frontend UI/UX decisions are governed by `PRODUCT.md` (register: product; users, purpose, positioning, anti-references) and `DESIGN.md` (visual system: colors, typography, elevation, components — "The Living Canopy" theme). Read both before designing or reviewing frontend changes; DESIGN.md wins on visual decisions, PRODUCT.md wins on strategic/voice decisions.

---

## The one rule that governs everything

> `api/` never runs agent logic. `worker/` never serves HTTP. `core/` never runs — it is a library.

Every structural question resolves from this. If you are writing an LLM call inside a router, or an HTTP request inside a job, stop.

---

## Separation of concerns

### Three processes, three responsibilities

| Process | Does | Never |
| --- | --- | --- |
| `api/` | validate, store, enqueue, query | LLM calls, LangGraph, agent decisions |
| `worker/` | LLM calls, graph execution, scoring, memory writes | serve HTTP, business-level validation |
| `core/` | shared models, coordination, eventing, intelligence, memory | own an entrypoint or run directly |

### Where does X belong?

- Both `api/` and `worker/` need it → `core/`
- Only ever invoked by an ARQ job → `worker/jobs/`
- Pure logic with no dependency on ARQ, HTTP, or Redis Streams → `core/`
- Serving, validating, or querying data for a customer → `api/`
- Needed by multiple worker handlers but is worker-specific (calls `arq_queue`) → `worker/coordination/`

### Intelligence layer

| File | Single job |
|---|---|
| `registry.py` | In-memory model catalog. Stores `ModelEntry` dicts. Nothing else. |
| `sync.py` | Reconciles registry → DB at startup. Never called at request time. |
| `routing_config.py` | Merges platform defaults + workspace overrides into a routing table. |
| `llm_router.py` | Dispatches LLM calls. Resolves model, builds client, applies semaphore. |
| `call_types.py` | Enum of call types. No logic. |
| `prompts/` | One file per call type. Returns a prompt string. No dispatch, no response parsing. |
| `structured_call.py` | Calls the LLM for a call type via `LLMRouter`, parses the response, retries once on `ValidationError`. `call_and_parse` re-raises if the retry also fails; `run` falls back to a caller-provided default instead. No dispatch logic of its own, no prompt text. |
| `context.py` | Frozen dataclasses (`AgentContext`, `TaskEvaluationContext`) describing the inputs a prompt reasons about. No logic. |
| `signals.py` | Pure classification helpers (e.g. `classify_influence` → `InfluenceTier`) shared by prompts and non-LLM code (`sample_metrics.py`'s hub detection) so the same thresholds mean the same thing everywhere. |
| `enrichment.py` | Task-enrichment pipeline: calls the LLM via `structured_call`, honours caller-supplied `EnrichmentOverrides` to skip fields already known. No prompt text, no dispatch of its own. |
| `reflection/` | `types.py` — frozen `ReflectContext`/`PipelineResult` dataclasses built from ORM state before the session closes. `pipeline.py` — declarative `PipelineStage` entries (the reflection cascade), no LLM calls or execution logic of its own. |

---

## Service layer (`api/`)

### Commands, DTOs, ORM boundary

Every `api/` service follows one pattern: **Command in → ORM stays inside → DTO out**. The ORM model never crosses the service boundary into a router.

```python
# correct — router builds a Command; service returns a DTO
cmd = CreateTaskCommand(workspace_id=workspace.id, title=body.title, ...)
task: TaskData = await service.create(cmd)
return TaskResponse.model_validate(task)

# wrong — ORM returned from service, leaks into router
task: Task = await service.create(body)
```

### Commands (write intents)

Frozen dataclasses defined in the service file. The router constructs them from HTTP input; the service never imports from `api/schemas/`.

```python
@dataclass(frozen=True)
class CreateTaskCommand:
    workspace_id: uuid.UUID
    title: str
    ...
```

Read operations take primitive IDs only — no Command needed.

### DTOs with explicit `from_domain()`

Frozen dataclasses defined in the service file. Use an explicit allowlist in `from_domain()` rather than introspection — this is the only safe pattern when fields must be excluded for security.

```python
@dataclass(frozen=True)
class WorkspaceData:
    id: uuid.UUID
    name: str
    # webhook_secret intentionally absent — HMAC key, never in API responses

    @classmethod
    def from_domain(cls, ws: Workspace) -> WorkspaceData:
        return cls(id=ws.id, name=ws.name, ...)  # explicit — no getattr loop
```

`Snapshot` subclasses in `core/eventing/` use type-hint introspection because they capture everything. Service DTOs use explicit mapping because they exclude sensitive fields. Do not conflate these two patterns.

### ORM in, DTO out for updates

`require_workspace()` in `deps.py` is auth infrastructure — it provides the Workspace ORM model as an auth token. Pass it directly to the service's `update()` method to avoid a second DB read. The service accepts ORM in and returns DTO out.

```python
async def update(self, ws: Workspace, cmd: UpdateWorkspaceCommand) -> WorkspaceData:
    # ws loaded by require_workspace() — no second DB read needed
    ...
    return WorkspaceData.from_domain(ws)
```

### Hard rules for services

- Services never call `session.commit()` — the caller (router) commits when needed.
- Services never import from `api/schemas/` — the boundary runs between schemas and services.
- Services never raise `HTTPException` — return `None` and let the router decide the status code.
- Response schemas must have `model_config = {"from_attributes": True}` so `model_validate(dto)` works on frozen dataclasses.

### The session.commit() exception in `create_task`

`create_task` commits explicitly before `arq_queue.enqueue_job()`. This is the only router that does this. The worker's fresh session must see the task row before the job runs. `service` and `session` share the same `AsyncSession` via FastAPI dep deduplication — committing the session also commits the service's writes.

---

## KISS — Keep It Simple

### Pure functions for pure logic

Bid scoring, skill matching, capacity factors, influence transforms — these are pure functions. No I/O, no async, no DB reads.

```python
# correct — pure function, all state passed in by the caller
def compute_bid_score(agent_skills, agent_influence, ...) -> float: ...

# wrong — hidden I/O inside what looks like a calculation
async def compute_bid_score(agent_id, task_id, session) -> float: ...
```

### No LLM in the coordination layer

`core/coordination/` is deterministic. `compute_bid_score`, `attempt_reservation`, `TaskStateMachine` — none call an LLM or read the database.

### No preprocessing — memory retrieval is a tool call

Agents retrieve episodic, procedural, and social memory mid-execution via tool calls. It is not injected upfront.

---

## Decoupling

### Interfaces over concrete types

The bus is typed against `BusProtocol`, not `RedisBus`. Tests swap in `InMemoryBus`. Vendor implementations satisfy `VendorProvider` ABC. `LLMRouter` works against the ABC, not any specific vendor SDK.

```python
# correct — decoupled from transport
async def decompose_and_publish(agent, parent_task, subtask_specs, session, bus: BusProtocol): ...

# wrong — coupled to Redis
async def decompose_and_publish(..., redis: Redis): ...
```

### Self-registration over central wiring

Importing a vendor package is the act of registering it. `core/vendors/anthropic/__init__.py` calls `registry.add_model(...)` as a module-level side effect. Adding a vendor: create the package and add one import line to the lifespan hook.

### Parse external dicts at the boundary — never spelunk them downstream

Any external system that hands you a raw `dict` (ARQ job context, webhook payload, Redis Stream message) must be parsed into a **frozen dataclass** at the entry point.

```python
# correct — one classmethod owns ARQ's dict keys
@dataclass(frozen=True)
class ArqJobMeta:
    job_id:  str | None
    job_try: int

    @classmethod
    def from_ctx(cls, ctx: dict[str, Any]) -> ArqJobMeta:
        return cls(job_id=ctx.get("job_id"), job_try=ctx.get("job_try", 1))

# wrong — dict-spelunking scattered through job functions
job_id  = ctx.get("job_id")
```

### Inject the minimum surface — not the full context

When a class or function needs one thing from a larger object, accept only that thing — not the object. The activity logger pattern is the canonical example: loggers receive `PublishFn`, not the bus.

```python
# correct — only needs redis.delete; inject that object
async def _release_to_pool(span, execution, task, redis: Redis, ...) -> None: ...

# wrong — receives full WorkerContext just to call one method
async def _release_to_pool(span, execution, task, wctx: WorkerContext, ...) -> None: ...
```

### ContextVar for ambient state — never thread it as a parameter

Infrastructure that sets itself on a `ContextVar` at entry (e.g. `JobSpan`) must be retrieved via the accessor at the site that needs it. Never pass it as a function argument through intermediate layers.

```python
# correct
span = current_span()
await span.emit(...)

# wrong — span threaded through every layer despite being on a ContextVar
result = await stage.fn(rctx, result, llm, memory, span)
```

### Stage and handler functions take domain objects only

Stage functions and handler `handle()` methods receive domain values (ORM objects, snapshots, scalars) — never infrastructure (span, session factory, bus, worker context).

```python
# correct — infrastructure resolved at the owning layer
async def _stage_reflect(rctx: ReflectContext, result: PipelineResult, llm: LLMRouter, memory: AgentMemory) -> PipelineResult: ...

# wrong
async def _stage_reflect(rctx, result, llm, memory, span: JobSpan) -> PipelineResult: ...
```

### TYPE_CHECKING for circular avoidance

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.models.tasks import Task
```

### Workspace-scoped Redis keys

Every Redis key that varies by workspace must include `workspace_id`:

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

`EventBus` does not survive process restart. `RedisBus` is for events that must reach other processes or survive crashes. Never conflate them.

### Producers never touch the bus directly

```python
# correct — logger is the only producer interface
await logger.created(task)

# wrong — domain code coupling to the event model
await bus.apublish(TaskCreatedEvent(...))
```

Loggers receive `PublishFn = Callable[[DomainEvent], Awaitable[None]]` at construction — never the bus directly. Method names describe the domain action (`logger.created`, `logger.updated`, `logger.deleted`).

### API routers never publish directly

The session dependency (`Depends(get_db)`) commits *after* the router function returns — there is no point in a router's own body that runs after commit, so a router cannot safely sequence "publish only if the write actually persisted" by simple code placement the way a worker job can (see below). If an endpoint needs to trigger an event-driven side effect tied to its own write, commit first, then enqueue an ARQ job — mirroring `create_task`'s existing `session.commit()`-then-`enqueue_job()` pattern — and let that job do the publishing from its own worker-owned session scope. Never wire an activity logger into a router.

### Publish only after the session closes

```python
# correct — worker job owns its session scope; publish is sequential code after it
async with get_session() as session:
    task_repo.save(task)
await logger.updated(before, task)   # after the `async with` block, after commit

# wrong — still inside the open transaction; a commit failure after this
# leaves a notification for a write that never persisted
async with get_session() as session:
    task_repo.save(task)
    await logger.updated(before, task)
```

A function that participates in a caller's transaction (e.g. `decompose_subtasks()`) should never accept a publish-shaped dependency at all — that keeps the "publish after commit" invariant enforced by the function's own signature, not by remembering to place the call correctly.

### Snapshots must be taken before the session closes

```python
# correct — before snapshot captured before mutation
before = TaskSnapshot.from_domain(task)
task.status = "in_progress"
await logger.updated(before, task)

# wrong — snapshot taken after mutation
task.status = "in_progress"
before = TaskSnapshot.from_domain(task)   # reads mutated state
```

`Snapshot.from_domain()` uses type-hint introspection to map all fields by name. Override it when field names diverge or values need transformation. This is distinct from service DTOs which use explicit allowlist mapping — see the Service layer section.

### Events live in `core/eventing/events/`, import nothing from the domain

Event files import only from `core/eventing/bus/common.py` and stdlib. This keeps the event model dependency-free and importable in isolation.

### Handler registration

All handlers run fire-and-forget, registered once at startup via `bus.bind()`. Use wrappers from `core/eventing/bus/handlers.py`: `Retry`, `SyncToAsync`, `Filtering`. Call `await bus.drain_pending()` in both FastAPI and ARQ shutdown hooks.

---

## Single responsibility

| Class / function | Does | Never |
| --- | --- | --- |
| `ModelRegistry` | Maps `model_id → ModelEntry` | Builds models, reads DB, knows about vendors |
| `sync_models()` | Reconciles registry → DB at startup | Runs at request time |
| `resolve_routing()` | Merges platform defaults + workspace overrides | Dispatches anything |
| `LLMRouter` | Resolves model, builds client, invokes it | Registers models, knows global catalog |
| `TaskStateMachine` | Validates and applies status transitions | Loads from DB, publishes events |
| `decompose_subtasks()` | Writes subtasks | Calls the LLM, commits the session, publishes events |
| `XActivityLogger` | Constructs and publishes events | DB access, handler logic |
| API routers | Validate input, call service, translate to HTTP | Business logic, LLM calls |
| Service classes | Accept Commands, return DTOs | Commit sessions, import HTTP schemas |

---

## Typing

### No bare container types — always parameterise

```python
ctx: dict[str, Any]      # correct
ctx: dict                 # wrong
```

### Use `collections.abc` for structural types

Import `Callable`, `Awaitable`, `AsyncGenerator`, `AsyncIterator`, `Mapping` from `collections.abc`, not `typing`.

### Read-only mappings typed as `Mapping`, not `dict`

When a parameter or field is only ever read from, use `Mapping[K, V]`. Makes the read-only contract explicit.

### Named exceptions for distinguishable catch clauses

Raise a named subclass rather than a bare `RuntimeError` when callers need to catch a specific failure mode.

```python
class NoActiveSpanError(RuntimeError): ...
raise NoActiveSpanError("No active JobSpan — called outside a job context")
```

### Single source of truth for domain invariants

```python
TaskStateMachine.is_terminal(status)   # correct
status in TERMINAL_STATUSES             # wrong — duplicates the invariant and will drift
```

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

All LLM calls for agent reasoning go through `LLMRouter` and are invoked from `worker/jobs/` only. Never add LLM calls to routers or middleware.

### registry.py must stay dependency-free

`core/intelligence/registry.py` has no DB import, no vendor SDK, no credentials, no settings import. Any circular import between the registry and a vendor package causes silent registration failure.

### Chroma always uses the HTTP client

```python
client = chromadb.HttpClient(url="http://chroma:8001")   # correct
client = chromadb.Client()                                 # wrong — creates local directory
```

### Alembic for every schema change

Every change to a `core/models/` class that affects the database schema needs a migration file in the same PR:
```bash
cd core && alembic revision --autogenerate -m "describe the change"
```

### webhook_secret is a credential, not a hash

`workspace.webhook_secret` is stored as plaintext — HMAC signing requires the raw secret. Treat it like a private key: never include it in API responses, never log it, never SELECT it except in the job that signs deliveries. It is excluded from `WorkspaceData` for this reason.

### Config changes touch both files

`config.py` defaults apply everywhere `.env` is absent. `.env` wins at runtime. Update both in the same commit.

### LangGraph graphs compile at worker startup

Compile in the ARQ `startup()` hook and reuse across all jobs. Never compile inside a job function.

---

## Comments

Default to writing no comments. Add one only when the **why** is non-obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug, behaviour that would surprise a reader. Never write multi-paragraph docstrings or multi-line comment blocks — one short line max.

---

## Development notes

- Ollama must run natively on the host OS, not inside Docker. For development without a local GPU, use `LLM_BACKEND=anthropic`.
- Auth middleware maps Clerk claims (`clerk_user_id`, `clerk_org_id`) → internal UUIDs. Downstream code trusts `request.state.org_id` and never re-validates Clerk tokens.
- The `models` table is written only by `sync_models()` at startup. Never write to it at request time.
- Workspace routing config (`workspace_model_routing`) is the only place per-workspace model preferences live.
- A root-level `Makefile` verifies backend changes: `make check` runs lint (ruff), format-check, mypy, `import-linter` (enforces the process/layer boundaries in this file — see `make arch`), and the full test suite across `api`/`core`/`worker`. Run `make setup` once (or after adding a dev/test dependency) to sync the shared workspace venv with its dev+test extras. Individual targets (`make lint`, `make typecheck`, `make arch`, `make test`, `make test-api`, etc.) are also available — see `make help`.

---

## Frontend (`frontend/`)

### State ownership

Server state (anything from the API or WebSocket) → TanStack Query. UI-only state (open panels, view modes, ephemeral config) → Zustand. Never put API response data in Zustand.

### Client boundary

Place a single `'use client'` in `app/orgs/[orgId]/workspaces/[workspaceId]/layout.tsx`. Every component inside that subtree inherits the boundary — none need their own directive. Do not add `'use client'` to individual dashboard leaf components.

### Cache invalidation — always use Orval-generated key factories

```ts
// correct — factory stays in sync with the generated hook
queryClient.invalidateQueries({
  queryKey: getListTasksWorkspacesWorkspaceIdTasksGetQueryKey(workspaceId),
})

// wrong — hand-written key that can drift
queryClient.invalidateQueries({ queryKey: ['workspaces', workspaceId, 'tasks'] })
```

### `invalidateQueries` vs `setQueryData`

Use `invalidateQueries` when the server has authoritative state (task completions, emergence events, agent skill updates — the event carries deltas, not full state). Use `setQueryData` only when the WebSocket event carries the complete new state and an immediate local update is preferable to a round trip.

### Axios — never import directly in components

All HTTP goes through Orval's custom fetcher (`src/api/client.ts`). Components never import from `axios`. The `AXIOS_INSTANCE` in `client.ts` is the only place to configure the base URL, auth interceptors, and error normalisation.

### WebSocket event validation — Zod at the boundary

Every new backend event type needs a Zod schema added to the `WorkspaceEvent` discriminated union in `frontend/src/hooks/workspace/useWorkspaceStream.ts`. All incoming messages go through `WorkspaceEvent.safeParse()` before touching the query cache — malformed events are silently discarded. The `discriminatedUnion` on `type` enables exhaustiveness checking: adding an event to the union without handling it in the switch is a compile error.### Orval regeneration workflow

After any backend schema change:

```bash
bun run orval          # regenerate the API client
bun run tsc --noEmit   # type errors = broken contracts
```

Generated files in `src/api/generated/` are committed to git. CI runs `tsc --noEmit` without a live API server — a schema drift that is not regenerated blocks the PR.

### Types and Zod schemas — how the generated layer works

Orval generates two things per model type:

- `model/agentResponse.ts` — TypeScript interface (compile-time only, not exported from the barrel)
- `model/agentResponse.zod.ts` — Zod schema that is both a runtime validator and the TypeScript type source

`model/index.ts` exports **only** from `.zod.ts` files. This means every import from `@/api/generated/model` gives you a Zod schema (a runtime value), not a bare TypeScript interface.

**Rules that must not regress:**

```ts
// correct — flat response, type comes from the barrel (Zod source)
import type { AgentResponse } from '@/api/generated/model'
const agents = data ?? []           // data is AgentResponse[] directly

// wrong — old wrapper shape no longer exists
const agents = data?.data ?? []     // data is not { data: AgentResponse[] }
const ok = response.status === 200  // HTTP status is not on the response object
```

Sub-types that are inlined into parent schemas (`AgentResponseSkills`, `UpdateWorkspaceRequestStatus`, etc.) have no `.zod.ts` file and are not in the barrel. Import them directly from their `.ts` file:

```ts
// correct — not in barrel, import the specific file
import { UpdateWorkspaceRequestStatus } from '@/api/generated/model/updateWorkspaceRequestStatus'

// wrong — not exported from the barrel index
import { UpdateWorkspaceRequestStatus } from '@/api/generated/model'
```

Every `customInstance` call in the generated hooks passes the Zod schema as a third argument. `client.ts` calls `schema.parse(res.data)` at runtime — if the backend sends a shape that doesn't match, it throws immediately at the HTTP boundary, not deep in the UI.

`httpClient: 'axios'` in `orval.config.ts` means generated hooks receive flat response types. If you ever see `Argument of type '{ url: string, method: string }' is not assignable to parameter of type 'string'` after regenerating, it means the config changed — do not change `customInstance` to accept a URL string.

### Icons

Phosphor icons only (`@phosphor-icons/react`, `components.json`'s `iconLibrary: "phosphor"`). No other icon library, no inline SVGs for UI icons. All icons are re-exported through `frontend/src/lib/icons.ts` using an `Icon*` naming convention (e.g. `Robot as IconAgent`) — import from that barrel, not directly from the package. See ADR: shadcn/ui on Base UI primitives, Phosphor icons.

### Framer Motion

Use only for animations that are genuinely stateful or physics-based. Do not reach for it when a CSS transition suffices — it adds bundle weight.

### Adding a new feature

1. Check if the backend endpoint exists. If so, `bun run orval` — the hook is already generated.
2. Server state → TanStack Query. UI-only state → Zustand.
3. If the feature responds to live events, add the Zod schema to the `WorkspaceEvent` union first.
4. Place the component inside `app/orgs/[orgId]/workspaces/[workspaceId]/` — it inherits the client boundary and WebSocket connection automatically.
5. Run `bun run tsc --noEmit` before opening a PR.

---

## Agent skills

### Issue tracker

Issues live in **Linear** (https://linear.app/apprise-labs). See `docs/agents/issue-tracker.md` for projects, labels, priority conventions, and MCP tool usage.

### Triage labels

Default label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context repo: `CONTEXT-MAP.md` at root points to per-area `CONTEXT.md` files under `docs/backend/` and `docs/frontend/`. See `docs/agents/domain.md`.
