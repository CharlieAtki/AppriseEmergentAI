# Event Bus

## Overview

Apprise uses an in-process event bus to decouple producers (routers, worker jobs) from consumers (audit loggers, governance hooks, metrics collectors). A producer fires an event and moves on — it has no knowledge of who is listening or what they do.

There are two transport layers:

| Layer | Class | Use case |
|-------|-------|----------|
| In-process | `InProcessBus` | Same-process side effects: audit logging, cache invalidation, metrics |
| Cross-process | `RedisBus` | Durable delivery to other processes via Redis Streams |

This document covers the in-process layer. The Redis layer is a follow-on.

---

## Architecture

```
Producer                    InProcessBus                 Consumers
────────                    ────────────                 ─────────
TaskActivityLogger          publish(event)
  └─ task_created(task)  ──────────────────────────►  AuditLogHandler  (bind)
                             walks MRO                  MetricsHandler   (bind)
                             transactional first         GovernanceHandler (bind_transactional)
```

Producers never import handlers. Handlers never import producers. The bus is the only shared reference.

---

## Core types (`core/bus/common.py`)

### `Snapshot`

A frozen dataclass capturing an entity's state at a point in time. Immutable by design — a snapshot is a fact, not a live object.

```python
@dataclasses.dataclass(frozen=True, kw_only=True)
class TaskSnapshot(Snapshot):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: str
    ...
```

`Snapshot.from_domain(model)` constructs a snapshot by matching field names directly from a SQLAlchemy model. No queries are triggered — only already-loaded scalar attributes are read. Override `from_domain` on the concrete class when field names diverge or nested snapshots are needed.

### `DomainEvent`

Base class for all events. Auto-generates `event_id` (UUID) and `timestamp` (UTC) on every instance.

```python
@dataclasses.dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### `StateActionEvent[T]`

Carries `state: T` — the entity snapshot after a create or delete.

### `StateChangeEvent[T]`

Extends `StateActionEvent[T]` with `before: T`. Used for updates.

```python
event.after          # snapshot after the change (alias for state)
event.before         # snapshot before the change
event.changes        # frozenset of field names that differ
event.changed("status")  # True/False — did this specific field change?
```

---

## Concrete events (`core/events/`)

### Tasks (`core/events/task_events.py`)

| Event | Type | When |
|-------|------|------|
| `TaskCreatedEvent` | `StateActionEvent[TaskSnapshot]` | Task row inserted |
| `TaskUpdatedEvent` | `StateChangeEvent[TaskSnapshot]` | Task row modified |
| `TaskDeletedEvent` | `StateActionEvent[TaskSnapshot]` | Task row deleted |

### Agents (`core/events/agent_events.py`)

| Event | Type | When |
|-------|------|------|
| `AgentCreatedEvent` | `StateActionEvent[AgentSnapshot]` | Agent row inserted |
| `AgentUpdatedEvent` | `StateChangeEvent[AgentSnapshot]` | Agent row modified |
| `AgentDeletedEvent` | `StateActionEvent[AgentSnapshot]` | Agent row deleted |

---

## Handler interface (`core/bus/handlers.py`)

```python
class AsyncEventHandler(ABC, Generic[E]):
    @abstractmethod
    async def handle(self, event: E) -> None: ...
```

One ABC, async only. There is no sync variant — the stack is `asyncpg` + ARQ throughout.

---

## `InProcessBus` (`core/bus/in_process_bus.py`)

### Registration

```python
bus = InProcessBus()

# Fire-and-forget — errors caught and logged, publisher does not wait
bus.bind(TaskCreatedEvent, AuditLogHandler())

# Transactional — awaited before publish() returns, errors propagate to caller
bus.bind_transactional(AgentDeletedEvent, GovernanceHandler())

# Bind a handler to multiple unrelated event types
bus.bind([TaskCreatedEvent, AgentCreatedEvent], MetricsHandler())
```

### MRO routing

Handlers are resolved by walking the full MRO of the published event type. A handler bound to a base class automatically receives all subclasses — no separate registrations needed.

```python
# This handler receives TaskCreatedEvent, TaskUpdatedEvent, TaskDeletedEvent
bus.bind(TaskEvent, CatchAllHandler())
```

### Publishing

```python
await bus.publish(event)
# Transactional handlers run first (blocking)
# Fire-and-forget handlers are scheduled via asyncio.create_task
```

### Graceful shutdown

Call `wait_pending()` in your shutdown hook to drain in-flight fire-and-forget tasks before the process exits.

```python
# FastAPI lifespan or ARQ shutdown
await bus.wait_pending()
```

---

## Activity loggers (`core/activity/`)

Activity loggers are thin producer facades. Their only job is to construct the correct event from a SQLAlchemy model and forward it to a `publish` callable. They know nothing about the bus, handlers, or dispatch.

### `PublishFn`

```python
PublishFn = Callable[[DomainEvent], Awaitable[None]]
```

The bus's `publish` method satisfies this type. Loggers hold a reference to it — never to the bus directly.

### Usage pattern

```python
class TaskActivityLogger(ActivityLogger):
    async def task_created(self, task: Task) -> None:
        snapshot = TaskSnapshot.from_domain(task)
        await self._publish(TaskCreatedEvent(state=snapshot, workspace_id=task.workspace_id))

    async def task_updated(self, before: Task, after: Task) -> None:
        await self._publish(TaskUpdatedEvent(
            state=TaskSnapshot.from_domain(after),
            before=TaskSnapshot.from_domain(before),
            workspace_id=after.workspace_id,
        ))

    async def task_deleted(self, task: Task) -> None:
        snapshot = TaskSnapshot.from_domain(task)
        await self._publish(TaskDeletedEvent(state=snapshot, workspace_id=task.workspace_id))
```

---

## Wiring

### FastAPI (`api/deps.py`)

The bus lives on `app.state.bus`, set during the FastAPI lifespan. Dependency factories inject `publish` into loggers at request time — endpoints never touch the bus directly.

```python
def get_bus(request: Request) -> InProcessBus:
    return request.app.state.bus

def get_event_publisher(bus: InProcessBus = Depends(get_bus)) -> PublishFn:
    return bus.publish

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
    await logger.task_created(task)
```

### Worker

The worker has no FastAPI DI. Construct loggers directly from `WorkerContext`:

```python
logger = TaskActivityLogger(wctx.bus.publish)
await logger.task_created(task)
```

---

## Adding a new domain area

1. **Define snapshot and events** in `core/events/<domain>_events.py`

```python
@dataclasses.dataclass(frozen=True, kw_only=True)
class ArtifactSnapshot(Snapshot):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    artifact_type: str
    status: str

@dataclasses.dataclass(frozen=True, kw_only=True)
class ArtifactCreatedEvent(StateActionEvent[ArtifactSnapshot]):
    workspace_id: uuid.UUID
```

2. **Add the activity logger** in `core/activity/<domain>_logger.py`

```python
class ArtifactActivityLogger(ActivityLogger):
    async def artifact_created(self, artifact: Artifact) -> None:
        snapshot = ArtifactSnapshot.from_domain(artifact)
        await self._publish(ArtifactCreatedEvent(state=snapshot, workspace_id=artifact.workspace_id))
```

3. **Export** from `core/events/__init__.py` and `core/activity/__init__.py`

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

**Why `kw_only=True` on all dataclasses?**
Multi-level dataclass inheritance breaks when parent fields have defaults and subclass fields do not. `kw_only=True` at every level eliminates the ordering constraint entirely.

**Why transactional before fire-and-forget?**
Transactional handlers are on the caller's critical path — their outcome must be settled before the endpoint returns. Scheduling fire-and-forget tasks before that would start side effects before the primary work is confirmed complete.

**Why MRO routing?**
It lets a handler subscribe to a category of events (`TaskEvent`) without enumerating every subtype. Adding a new concrete event is transparent to existing handlers registered on a base class.
