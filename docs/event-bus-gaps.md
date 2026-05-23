# Event Bus — Implementation Gaps

The event bus base layer (`EventBus`, `Snapshot`, `DomainEvent`, `StateActionEvent`,
`StateChangeEvent`, composable wrappers, activity loggers) is fully implemented.
The following gaps remain before the bus is operational end-to-end.

---

## 1. No handler DB session utility

**Gap:** Handlers run fire-and-forget, outside the FastAPI request lifecycle. They
cannot use the request-scoped `AsyncSession` from `get_session()`. There is currently
no utility for opening a short-lived session inside a handler.

**What is needed:** A context manager in `core/database.py` (or `core/bus/`) that
opens and closes a sync `Session` (for `SyncEventHandler`) or an `AsyncSession`
(for `EventHandler`) independently of any request or ARQ job:

```python
# sync — for SyncEventHandler subclasses
with get_handler_session() as session:
    workspace = session.get(WorkspaceModel, event.workspace_id)

# async — for EventHandler subclasses that do not offload to a thread
async with get_async_handler_session() as session:
    ...
```

This is the prerequisite for all concrete handlers.

---

## 2. No concrete handlers

**Gap:** No `EventHandler` or `SyncEventHandler` subclasses exist. The bus can
dispatch events but nothing is listening.

**What is needed:** Handler implementations per domain area. The first handlers are
likely to be audit logging and/or agent/task side-effect cleanup. Each handler
follows one of two patterns:

```python
# Pattern 1 — simple sync work, registered with SyncToAsync
class AgentCleanupHandler(SyncEventHandler[AgentDeletedEvent]):
    def handle(self, event: AgentDeletedEvent) -> None:
        try:
            with get_handler_session() as session:
                # clean up agent artefacts
        except Exception:
            logger.exception("Cleanup failed for agent %s", event.state.id)

# Pattern 2 — complex handler owning multiple sync helpers
class AgentAuditHandler(EventHandler[AgentDeletedEvent]):
    async def handle(self, event: AgentDeletedEvent) -> None:
        await asyncio.to_thread(self._handle_sync, event)

    def _handle_sync(self, event: AgentDeletedEvent) -> None:
        try:
            with get_handler_session() as session:
                self._write_audit_entry(session, event)
        except Exception:
            logger.exception("Audit write failed for agent %s", event.state.id)
```

Errors are always caught and logged inside the handler — do not rely solely on the
bus-level `_safe_handle` safety net.

---

## 3. `EventBus` not wired into the FastAPI lifespan

**Gap:** `api/deps.py` references `request.app.state.bus` but no FastAPI lifespan
creates the `EventBus`, registers handlers, or drains the bus on shutdown.
Any request that reaches a dep that calls `get_bus()` will raise `AttributeError`.

**What is needed:** A lifespan context manager on the FastAPI app:

```python
from contextlib import asynccontextmanager
import asyncio
from core.bus.in_process_bus import EventBus

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    bus = EventBus(loop=loop)

    # Register handlers here
    # bus.bind(AgentDeletedEvent, SyncToAsync(AgentCleanupHandler()))

    app.state.bus = bus
    yield
    await bus.drain_pending()
    await bus.stop_subscribers()

app = FastAPI(lifespan=lifespan)
```

---

## 4. `EventBus` missing from `WorkerContext`

**Gap:** `WorkerContext` holds `bus: RedisBus` (the Redis Streams bus) but has no
`EventBus`. Worker jobs cannot call `wctx.bus.apublish(event)` for in-process events,
and cannot construct activity loggers from the worker.

**What is needed:** Add `event_bus: EventBus` to `WorkerContext` and wire it in
`WorkerContext.build()`:

```python
@dataclass(frozen=True)
class WorkerContext:
    bus: RedisBus        # Redis Streams — durable cross-process events
    event_bus: EventBus  # in-process — same-process side effects
    ...
```

In `startup()`:
```python
loop = asyncio.get_running_loop()
event_bus = EventBus(loop=loop)
# bus.bind(...) — register worker-side handlers here
```

In `shutdown()`:
```python
await wctx.event_bus.drain_pending()
```

Worker jobs then construct loggers as:
```python
logger = TaskActivityLogger(wctx.event_bus.apublish)
```

---

## 5. No handler registration

**Gap:** `bus.bind(...)` is never called anywhere. Even when handlers exist and the
bus is wired, nothing will be dispatched until handlers are registered at startup.

**What is needed:** A registration block in each lifespan hook (FastAPI and ARQ)
that binds concrete handlers to their event types:

```python
bus.bind(AgentDeletedEvent, SyncToAsync(AgentCleanupHandler()))
bus.bind(TaskCreatedEvent, Retry(SyncToAsync(AuditLogHandler()), retry_on=(OperationalError,)))
```

This block grows as new handlers are added. It is the only place handler wiring
should appear — never at request time, never inside a job function.

---

## 6. No tests

**Gap:** No tests exist for `EventBus` dispatch, composable wrappers, activity loggers,
or `Snapshot.from_domain`.

**What is needed (priority order):**

| Test | What it covers |
|------|---------------|
| `test_event_bus.py` | `bind`, MRO routing, `apublish` fire-and-forget, `drain_pending` |
| `test_handlers.py` | `Retry` backoff, `Filtering` predicate, `Timeout` cancellation, `SyncToAsync` thread dispatch |
| `test_activity_loggers.py` | `TaskActivityLogger.created` / `updated` / `deleted` publish correct events; `AsyncMock` as publish callable |
| `test_snapshots.py` | `from_domain` for flat fields, nested snapshots, `tuple[Snapshot, ...]` collections, nullable snapshot fields |

---

## Summary

| Gap | Prerequisite for |
|-----|-----------------|
| Handler DB session utility | All concrete handlers |
| Concrete handlers | Any real side effects |
| FastAPI lifespan wiring | All API-triggered events reaching handlers |
| `EventBus` in `WorkerContext` | Worker jobs publishing in-process events |
| Handler registration | Any handler actually running |
| Tests | Confidence in dispatch correctness and wrapper behaviour |

Close gaps 1 and 3–4 first — without session utility and bus wiring, handlers cannot
be written or tested in context.