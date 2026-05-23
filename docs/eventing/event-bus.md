# Event Bus

## Overview

Apprise uses an event bus to decouple producers (routers, worker jobs) from consumers (audit
loggers, governance hooks, metrics collectors, bidding logic). A producer fires an event and
moves on — it has no knowledge of who is listening or what they do.

There are two transport layers:

| Layer | Class | Use case |
|-------|-------|----------|
| In-process | `EventBus` | Same-process side effects: audit logging, cache invalidation, metrics, rollup |
| Cross-process | `RedisBus` | Durable delivery to other processes via Redis Streams |

The two buses are **not interchangeable**. `EventBus` does not survive process restart and never
should — it is for side effects the current process cares about. `RedisBus` is for events that
must reach other processes or survive crashes. The `TaskStreamSubscriber` bridges them: it
consumes off `RedisBus` and publishes typed events onto the in-process `EventBus`, so all
business logic remains in `EventHandler` implementations regardless of where the event originated.

### Choosing the right bus

Use the in-process `EventBus` when:

- The triggering pod already has the context needed to act — the ORM instance is in memory,
  the session just committed, no extra DB round-trip is needed to reconstruct state.
- The work is a local side effect of what just happened on this pod (rollup, audit log, cache
  invalidation, metrics).
- Serialising enough state for another pod to handle it would replicate what the DB query
  already does more cheaply in-process.

Use `RedisBus` when:

- The work can be handled by any pod — there is no advantage to keeping it on the pod where
  the event originated.
- The message must survive the current pod going away (durability via the PEL).
- You are coordinating across pods: bidding, social memory writes, anything where multiple
  workers compete or cooperate.

**Concrete example — why `RollupSubtaskHandler` is in-process:**
The pod that just committed `task.status = "completed"` has the `TaskSnapshot` in memory and
the DB session already closed cleanly. Firing `TaskUpdatedEvent` on the local `EventBus` costs
nothing — no serialisation, no network hop. To do the same rollup over Redis Streams, you would
need to serialise the task's status, `parent_task_id`, `workspace_id`, and
`coordinator_agent_id` so another pod could reconstruct enough context to query siblings and
transition the parent. That is slower, more complex, and buys nothing — any pod would
immediately re-query the DB anyway. The triggering pod is the right place for this work.

---

## Architecture

### In-process path (same-process domain events)

```
Producer                    EventBus                       Consumers
────────                    ────────                       ─────────
TaskActivityLogger
  └─ updated(task)  ──────────────────────────────►  RollupSubtaskHandler  (bind)
                            walks MRO                AuditLogHandler        (bind)
                            all fire-and-forget
```

### Cross-process path (Redis Streams → in-process)

```
Redis Stream "stream:task"
  └─ TaskStreamSubscriber (ExternalEventSubscriber)
       │  _parse_stream_event() → typed DomainEvent
       └─ event_bus.apublish(stream_event)
            │
            ├─ TaskBiddingHandler      (bind TaskCreatedStreamEvent)
            └─ SocialMemoryHandler     (bind TaskCompletedStreamEvent)
```

Producers never import handlers. Handlers never import producers. The bus is the only shared
reference in both paths.

---

## Core types (`core/eventing/bus/common.py`)

### `Snapshot`

A frozen dataclass capturing an entity's state at a point in time. Immutable by design — a
snapshot is a fact, not a live object.

```python
@dataclass(frozen=True, kw_only=True)
class TaskSnapshot(Snapshot):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: str
    ...
```

`Snapshot.from_domain(model)` constructs a snapshot by matching field names to attributes on the
domain object via `get_type_hints`. It handles three cases:

- **Scalar values** — copied directly.
- **Nested snapshots** — fields declared as `SnapshotSubclass` or `SnapshotSubclass | None` are
  constructed recursively via `from_domain`.
- **Snapshot collections** — fields declared as `tuple[SnapshotSubclass, ...]` accept any
  iterable and materialise it as a tuple, calling `from_domain` on each element.

No queries are triggered — only already-loaded attributes are read. Override `from_domain` on
the concrete class when field names diverge or values need transformation.

### `DomainEvent`

Base class for all events. Auto-generates `event_id` (UUID) and `timestamp` (UTC) on every
instance.

```python
@dataclass
class DomainEvent(ABC):
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### `StateActionEvent[T]`

Carries `state: T` — the entity snapshot after a create or delete.

### `StateChangeEvent[T]`

Extends `StateActionEvent[T]` with `before: T`. Used for updates where handlers need to know
what changed.

```python
event.after          # snapshot after the change (alias for state)
event.before         # snapshot before the change
event.changes        # frozenset of field names that differ
event.changed("status")  # True/False — did this specific field change?
```

Only use `StateChangeEvent` when a handler actually calls `event.changed()` or `event.changes`.
For notifications where only the resulting state matters, `StateActionEvent` is simpler.

---

## Concrete events (`core/eventing/events/`)

### Domain events — in-process, full snapshots

These carry full ORM snapshots and are fired by activity loggers within the same process.

#### Tasks (`core/eventing/events/task_events.py`)

| Event | Type | When |
|-------|------|------|
| `TaskCreatedEvent` | `StateActionEvent[TaskSnapshot]` | Task row inserted |
| `TaskUpdatedEvent` | `StateChangeEvent[TaskSnapshot]` | Task row modified |
| `TaskDeletedEvent` | `StateActionEvent[TaskSnapshot]` | Task row deleted |

#### Agents (`core/eventing/events/agent_events.py`)

| Event | Type | When |
|-------|------|------|
| `AgentCreatedEvent` | `StateActionEvent[AgentSnapshot]` | Agent row inserted |
| `AgentUpdatedEvent` | `StateChangeEvent[AgentSnapshot]` | Agent row modified |
| `AgentDeletedEvent` | `StateActionEvent[AgentSnapshot]` | Agent row deleted |

### Stream events — cross-process, partial payloads (`core/eventing/events/stream_events.py`)

These are fired by `TaskStreamSubscriber` after deserialising Redis Stream messages. They carry
only the coordination-relevant fields available in the wire format — not full ORM snapshots, which
cannot cross a process boundary.

| Event | Source message | Consumed by |
|-------|----------------|-------------|
| `TaskCreatedStreamEvent` | `task.created` on `stream:task` | `TaskBiddingHandler` |
| `TaskCompletedStreamEvent` | `task.completed` on `stream:task` | `SocialMemoryHandler` |

```python
@dataclass(kw_only=True)
class TaskCreatedStreamEvent(DomainEvent):
    task_id: uuid.UUID
    workspace_id: uuid.UUID
    required_skills: dict
    domain_tags: dict | None = None

@dataclass(kw_only=True)
class TaskCompletedStreamEvent(DomainEvent):
    task_id: uuid.UUID
    workspace_id: uuid.UUID
    completing_agent_id: uuid.UUID
    quality_score: float
    task_type: str
```

Stream events are distinct from domain events by design. `TaskCreatedStreamEvent` is not the
same as `TaskCreatedEvent`: the domain event carries a full `TaskSnapshot` from the ORM model;
the stream event carries only what was serialised into the Redis payload by the publisher.

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

class ExternalEventSubscriber(ABC):
    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
```

`EventBus.bind` accepts `EventHandler`. Use `SyncToAsync` to wrap a `SyncEventHandler` for
async dispatch. `ExternalEventSubscriber` is for any external source (Redis Streams, webhooks,
etc.) managed via `start_subscribers` / `stop_subscribers`.

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
# Fire-and-forget handler for a domain event
bus.bind(TaskCreatedEvent, AuditLogHandler())

# Bind one handler to multiple event types
bus.bind([TaskCreatedEvent, AgentCreatedEvent], MetricsHandler())

# Stream handler — fired by TaskStreamSubscriber after deserialising Redis payload
bus.bind(TaskCreatedStreamEvent, TaskBiddingHandler(redis=..., arq_queue=...))

# Register an external subscriber (starts when start_subscribers() is called)
bus.subscribe(TaskStreamSubscriber(bus=redis_bus, event_bus=bus, consumer="worker-1"))
```

### MRO routing

Handlers are resolved by walking the full MRO of the published event type. A handler bound to a
base class automatically receives all subclasses:

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

All handlers are fire-and-forget. A failing handler is logged and does not affect other handlers
or the publisher.

### Graceful shutdown

```python
# FastAPI lifespan or ARQ shutdown — order matters
await bus.stop_subscribers()   # stop external sources first
await bus.drain_pending()      # then drain in-flight handler tasks
```

---

## `TaskStreamSubscriber` (`worker/subscriber.py`)

`TaskStreamSubscriber` is the bridge between the `RedisBus` transport and the in-process
`EventBus`. It implements `ExternalEventSubscriber` and is managed entirely by the `EventBus`
lifecycle — no manual `asyncio.create_task` or task cancellation in startup/shutdown code.

```python
@dataclass
class TaskStreamSubscriber(ExternalEventSubscriber):
    bus: RedisBus       # Redis Streams source
    event_bus: EventBus # in-process bus to dispatch onto
    consumer: str       # unique per process — f"worker-{os.getpid()}"
```

`start()` spawns the consumer loop as a named asyncio task. `stop()` cancels it and awaits clean
exit. The loop calls `_parse_stream_event(payload)` to deserialise each message into a typed
event, then `event_bus.apublish(event)` to schedule all registered handlers fire-and-forget.
The `ack` is called in `finally` — it always fires regardless of handler outcome, preventing
messages from blocking the PEL indefinitely on handler failure.

`_parse_stream_event` returns `None` for unknown `event_type` values (DEBUG-logged, not
WARNING) so future event types produced by newer publishers don't crash older workers.

---

## Activity loggers (`core/eventing/activity/`)

Activity loggers are thin producer facades. Their only job is to construct the correct event
from a SQLAlchemy model and forward it to a `publish` callable. They know nothing about the bus,
handlers, or dispatch.

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

Method names describe the domain action. The class name already scopes the entity — no `task_`
prefix needed.

---

## Wiring

### FastAPI (`api/deps.py`)

The bus lives on `app.state.bus`, set during the FastAPI lifespan. Dependency factories inject
`apublish` into loggers at request time — endpoints never touch the bus directly.

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

### Worker (`worker/startup.py`)

The worker wires all handlers and the subscriber in the ARQ startup hook. Handler registration
must complete before `start_subscribers()` is called so the first deserialised stream event
always finds its handlers registered.

```python
async def startup(ctx):
    wctx = await WorkerContext.build(arq_queue)

    # In-process handlers
    wctx.event_bus.bind(TaskUpdatedEvent,         RollupSubtaskHandler(arq_queue=wctx.arq_queue))

    # Stream handlers (fired by TaskStreamSubscriber)
    wctx.event_bus.bind(TaskCreatedStreamEvent,   TaskBiddingHandler(redis=wctx.redis, arq_queue=wctx.arq_queue))
    wctx.event_bus.bind(TaskCompletedStreamEvent, SocialMemoryHandler(memory=wctx.memory))

    # Bridge: Redis Streams → in-process EventBus
    wctx.event_bus.subscribe(TaskStreamSubscriber(
        bus=wctx.bus,
        event_bus=wctx.event_bus,
        consumer=f"worker-{os.getpid()}",
    ))
    await wctx.event_bus.start_subscribers()

async def shutdown(ctx):
    await wctx.event_bus.stop_subscribers()   # cancel TaskStreamSubscriber
    await wctx.event_bus.drain_pending()      # drain in-flight handlers
    await wctx.bus.close()
    await wctx.redis.aclose()
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

## Adding a new Redis Stream event type

1. **Add the stream event** to `core/eventing/events/stream_events.py`

```python
@dataclass(kw_only=True)
class TaskExpiredStreamEvent(DomainEvent):
    task_id: uuid.UUID
    workspace_id: uuid.UUID
```

2. **Add a case to `_parse_stream_event`** in `worker/subscriber.py`

```python
case "task.expired":
    return TaskExpiredStreamEvent(
        task_id=uuid.UUID(payload["task_id"]),
        workspace_id=uuid.UUID(payload["workspace_id"]),
    )
```

3. **Create the handler** in `worker/handlers/<name>.py`

4. **Register** in `worker/startup.py`

```python
wctx.event_bus.bind(TaskExpiredStreamEvent, ExpiryCleanupHandler(...))
```

---

## Design decisions

**Why `PublishFn` instead of injecting the bus?**
Loggers hold the smallest possible surface area. A callable is easier to mock in tests
(`AsyncMock()`), easier to swap, and makes the logger's dependency explicit — it queues events,
nothing else.

**Why no `ActivityLogger` base class?**
A base class whose only content is `self._publish = publish` is pure ceremony. Each logger holds
its own callable. No shared behaviour means no shared base class.

**Why method names without the entity prefix?**
`logger.created(task)` is unambiguous — `TaskActivityLogger` already scopes the entity.
Repeating it as `logger.task_created(task)` is noise. Use domain action vocabulary rather than
CRUD: `skills_updated`, `status_changed`, `llm_changed` communicate *what happened*, not just
that a row was written.

**Why separate stream event types instead of reusing `TaskCreatedEvent`?**
`TaskCreatedEvent` carries a full `TaskSnapshot` built from an ORM model. The Redis payload
carries only what was serialised at publish time — a partial, coordination-focused subset.
Using the same type would either require lying about the snapshot fields or making them optional
everywhere, both of which introduce subtle bugs. The separate types make the contract explicit:
if you receive a `TaskCreatedStreamEvent`, you have IDs and skills; if you receive a
`TaskCreatedEvent`, you have the full entity state.

**Why `ExternalEventSubscriber` instead of a raw `asyncio.create_task`?**
Lifecycle uniformity. The ARQ shutdown hook calls `stop_subscribers()` and `drain_pending()` in
one place. A raw task requires manual tracking in `ctx`, a separate cancel, and correct ordering
around `drain_pending`. The subscriber ABC removes all of that from startup/shutdown code and
makes it impossible to forget the cancel or get the ordering wrong.

**Why composable wrappers instead of `bind_transactional`?**
A transactional mode forces a single binary choice on every handler. Composable wrappers
(`Retry`, `Timeout`, `Filtering`) express the same intent more precisely and can be combined.
`Retry(handler, retry_on=(OperationalError,))` is more informative than "this handler is
transactional".

**Why two publish paths (`publish` and `apublish`)?**
`apublish` is for async callers — FastAPI endpoints and ARQ jobs — and uses
`asyncio.ensure_future`. `publish` is for synchronous callers on a different thread and uses
`run_coroutine_threadsafe`. The async path is the normal one; the sync path exists for handlers
or callbacks that cannot be made async.

**Why MRO routing?**
It lets a handler subscribe to a category of events (`TaskEvent`) without enumerating every
subtype. Adding a new concrete event is transparent to existing handlers registered on a base
class.

**Why `kw_only=True` on event dataclasses?**
Multi-level dataclass inheritance breaks when parent fields have defaults and subclass fields do
not. `kw_only=True` at every level eliminates the ordering constraint entirely.
