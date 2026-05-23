# Event Bus

## Overview

Apprise uses an in-process event bus to decouple producers (routers, worker jobs) from consumers (audit loggers, governance hooks, metrics collectors). A producer fires an event and moves on — it has no knowledge of who is listening or what they do.

There are two transport layers:

| Layer | Class | Use case |
|-------|-------|----------|
| In-process | `EventBus` | Same-process side effects: audit logging, cache invalidation, metrics |
| Cross-process | `RedisBus` | Durable delivery to other processes via Redis Streams |

This document covers the in-process layer. The Redis layer is a follow-on.

---

## Architecture

```
Producer                    EventBus                     Consumers
────────                    ────────                     ─────────
TaskActivityLogger          apublish(event)
  └─ created(task)  ──────────────────────────────►  AuditLogHandler  (bind)
                             walks MRO                MetricsHandler   (bind)
                             all fire-and-forget       CleanupHandler  (bind + Retry)
```

Producers never import handlers. Handlers never import producers. The bus is the only shared reference.

---

## Core types (`core/eventing/bus/common.py`)

### `Snapshot`

A frozen dataclass capturing an entity's state at a point in time. Immutable by design — a snapshot is a fact, not a live object.

```python
@dataclass(frozen=True, kw_only=True)
class TaskSnapshot(Snapshot):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: str
    ...
```

`Snapshot.from_domain(model)` constructs a snapshot by matching field names to attributes on the domain object via `get_type_hints`. It handles three cases:

- **Scalar values** — copied directly.
- **Nested snapshots** — fields declared as `SnapshotSubclass` or `SnapshotSubclass | None` are constructed recursively via `from_domain`.
- **Snapshot collections** — fields declared as `tuple[SnapshotSubclass, ...]` accept any iterable and materialise it as a tuple, calling `from_domain` on each element.

No queries are triggered — only already-loaded attributes are read. Override `from_domain` on the concrete class when field names diverge or values need transformation.

### `DomainEvent`

Base class for all events. Auto-generates `event_id` (UUID) and `timestamp` (UTC) on every instance.

```python
@dataclass
class DomainEvent(ABC):
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### `StateActionEvent[T]`

Carries `state: T` — the entity snapshot after a create or delete.

### `StateChangeEvent[T]`

Extends `StateActionEvent[T]` with `before: T`. Used for updates where handlers need to know what changed.

```python
event.after          # snapshot after the change (alias for state)
event.before         # snapshot before the change
event.changes        # frozenset of field names that differ
event.changed("status")  # True/False — did this specific field change?
```

Only use `StateChangeEvent` when a handler actually calls `event.changed()` or `event.changes`. For notifications where only the resulting state matters, `StateActionEvent` is simpler.

---

## Concrete events (`core/eventing/events/`)

### Tasks (`core/eventing/events/task_events.py`)

| Event | Type | When |
|-------|------|------|
| `TaskCreatedEvent` | `StateActionEvent[TaskSnapshot]` | Task row inserted |
| `TaskUpdatedEvent` | `StateChangeEvent[TaskSnapshot]` | Task row modified |
| `TaskDeletedEvent` | `StateActionEvent[TaskSnapshot]` | Task row deleted |

### Agents (`core/eventing/events/agent_events.py`)

| Event | Type | When |
|-------|------|------|
| `AgentCreatedEvent` | `StateActionEvent[AgentSnapshot]` | Agent row inserted |
| `AgentUpdatedEvent` | `StateChangeEvent[AgentSnapshot]` | Agent row modified |
| `AgentDeletedEvent` | `StateActionEvent[AgentSnapshot]` | Agent row deleted |

---

## Handler interface (`core/eventing/bus/handlers.py`)

Three ABCs:

```python
class SyncEventHandler[E](ABC):
    @abstractmethod
    def handle(self, event: E) -> None: ...

class EventHandler[E](ABC):
    @abstractmethod
    async def handle(self, event: E) -> None: ...

class ExternalEventSubscriber[E](ABC):
    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
```

`EventBus.bind` accepts `EventHandler`. Use `SyncToAsync` to wrap a `SyncEventHandler` for async dispatch. `ExternalEventSubscriber` is for Redis Streams or other cross-process sources managed via `start_subscribers` / `stop_subscribers`.

### Composable wrappers

Behaviour is composed at the registration site, not inside handler bodies:

| Wrapper | Purpose |
|---------|---------|
| `SyncToAsync(handler)` | Run a `SyncEventHandler` in a thread via `asyncio.to_thread` |
| `Retry(handler, retry_on=..., fatal_on=..., max_attempts=3, backoff=1.0)` | Retry with exponential backoff |
| `Filtering(handler, predicate=...)` | Gate — handler only runs when `predicate(event)` is truthy |
| `Timeout(handler, seconds=...)` | Cancel handler if it exceeds the time limit |

Wrappers compose:

```python
bus.bind(AgentDeletedEvent,
    Retry(
        Timeout(SyncToAsync(ComplianceHandler()), seconds=30),
        retry_on=(TimeoutError, OperationalError),
    )
)
```

---

## `EventBus` (`core/eventing/bus/in_process_bus.py`)

### Construction

```python
loop = asyncio.get_running_loop()
bus = EventBus(loop=loop)
```

### Registration

```python
# Fire-and-forget — errors caught and logged
bus.bind(TaskCreatedEvent, AuditLogHandler())

# Bind one handler to multiple event types
bus.bind([TaskCreatedEvent, AgentCreatedEvent], MetricsHandler())

# Register an external subscriber (Redis Streams, etc.)
bus.subscribe(TaskStreamSubscriber())
```

### MRO routing

Handlers are resolved by walking the full MRO of the published event type. A handler bound to a base class automatically receives all subclasses:

```python
# Receives TaskCreatedEvent, TaskUpdatedEvent, TaskDeletedEvent
bus.bind(TaskEvent, CatchAllHandler())
```

### Publishing

```python
# From async callers (FastAPI endpoints, worker jobs) — normal path
await bus.apublish(event)

# From synchronous callers on a different thread
bus.publish(event)
```

All handlers are fire-and-forget. A failing handler is logged and does not affect other handlers or the publisher.

### Graceful shutdown

Call `drain_pending()` in your shutdown hook to await all in-flight tasks before the process exits:

```python
# FastAPI lifespan or ARQ shutdown
await bus.drain_pending()
await bus.stop_subscribers()
```

---

## Activity loggers (`core/eventing/activity/`)

Activity loggers are thin producer facades. Their only job is to construct the correct event from a SQLAlchemy model and forward it to a `publish` callable. They know nothing about the bus, handlers, or dispatch.

Logger methods read scalar attributes from their argument. This works even on detached SQLAlchemy instances — SQLAlchemy keeps cached scalar values in `__dict__` after detach.

### `PublishFn`

```python
PublishFn = Callable[[DomainEvent], Awaitable[None]]
```

`bus.apublish` satisfies this type. Loggers hold a reference to it — never to the bus directly.

### Usage pattern

```python
class TaskActivityLogger:
    def __init__(self, publish: PublishFn) -> None:
        self._publish = publish

    async def created(self, task: Task) -> None:
        snapshot = TaskSnapshot.from_domain(task)
        await self._publish(TaskCreatedEvent(state=snapshot, workspace_id=task.workspace_id))

    async def updated(self, before: TaskSnapshot, after: Task) -> None:
        await self._publish(TaskUpdatedEvent(
            state=TaskSnapshot.from_domain(after),
            before=before,
            workspace_id=after.workspace_id,
        ))

    async def deleted(self, task: Task) -> None:
        snapshot = TaskSnapshot.from_domain(task)
        await self._publish(TaskDeletedEvent(state=snapshot, workspace_id=task.workspace_id))
```

Method names describe the domain action. The class name already scopes the entity — no `task_` prefix needed.

---

## Wiring

### FastAPI (`api/deps.py`)

The bus lives on `app.state.bus`, set during the FastAPI lifespan. Dependency factories inject `apublish` into loggers at request time — endpoints never touch the bus directly.

```python
def get_bus(request: Request) -> EventBus:
    return request.app.state.bus

def get_event_publisher(bus: EventBus = Depends(get_bus)) -> PublishFn:
    return bus.apublish

def get_task_activity_logger(
    publish: PublishFn = Depends(get_event_publisher),
) -> TaskActivityLogger:
    return TaskActivityLogger(publish)
```

Endpoint usage:

```python
@router.post("/tasks")
async def create_task(
    ...,
    logger: TaskActivityLogger = Depends(get_task_activity_logger),
):
    task = ...  # create and flush
    await logger.created(task)
```

### Worker

The worker has no FastAPI DI. Construct loggers directly from `WorkerContext`:

```python
logger = TaskActivityLogger(wctx.bus.apublish)
await logger.created(task)
```

---

## Adding a new domain area

1. **Define snapshot and events** in `core/eventing/events/<domain>_events.py`

```python
@dataclass(frozen=True, kw_only=True)
class ArtifactSnapshot(Snapshot):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    artifact_type: str
    status: str

@dataclass(kw_only=True)
class ArtifactCreatedEvent(StateActionEvent[ArtifactSnapshot]):
    workspace_id: uuid.UUID
```

2. **Add the activity logger** in `core/eventing/activity/<domain>_logger.py`

```python
class ArtifactActivityLogger:
    def __init__(self, publish: PublishFn) -> None:
        self._publish = publish

    async def created(self, artifact: Artifact) -> None:
        snapshot = ArtifactSnapshot.from_domain(artifact)
        await self._publish(ArtifactCreatedEvent(state=snapshot, workspace_id=artifact.workspace_id))
```

3. **Export** from `core/eventing/events/__init__.py` and `core/eventing/activity/__init__.py`

4. **Add dep factory** to `api/deps.py`

```python
def get_artifact_activity_logger(
    publish: PublishFn = Depends(get_event_publisher),
) -> ArtifactActivityLogger:
    return ArtifactActivityLogger(publish)
```

---

## Design decisions

**Why `PublishFn` instead of injecting the bus?**
Loggers hold the smallest possible surface area. A callable is easier to mock in tests (`AsyncMock()`), easier to swap, and makes the logger's dependency explicit — it queues events, nothing else.

**Why no `ActivityLogger` base class?**
A base class whose only content is `self._publish = publish` is pure ceremony. Each logger holds its own callable. No shared behaviour means no shared base class.

**Why method names without the entity prefix?**
`logger.created(task)` is unambiguous — `TaskActivityLogger` already scopes the entity. Repeating it as `logger.task_created(task)` is noise. Use domain action vocabulary rather than CRUD: `skills_updated`, `status_changed`, `llm_changed` communicate *what happened*, not just that a row was written.

**Why composable wrappers instead of `bind_transactional`?**
A transactional mode forces a single binary choice on every handler. Composable wrappers (`Retry`, `Timeout`, `Filtering`) express the same intent more precisely and can be combined. `Retry(handler, retry_on=(OperationalError,))` is more informative than "this handler is transactional".

**Why two publish paths (`publish` and `apublish`)?**
`apublish` is for async callers — FastAPI endpoints and ARQ jobs — and uses `asyncio.ensure_future`. `publish` is for synchronous callers on a different thread and uses `run_coroutine_threadsafe`. The async path is the normal one; the sync path exists for handlers or callbacks that cannot be made async.

**Why MRO routing?**
It lets a handler subscribe to a category of events (`TaskEvent`) without enumerating every subtype. Adding a new concrete event is transparent to existing handlers registered on a base class.

**Why `kw_only=True` on event dataclasses?**
Multi-level dataclass inheritance breaks when parent fields have defaults and subclass fields do not. `kw_only=True` at every level eliminates the ordering constraint entirely.