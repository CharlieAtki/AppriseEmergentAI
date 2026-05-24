# Event Bus — Implementation Gaps

The event bus base layer (`EventBus`, `Snapshot`, `DomainEvent`, `StateActionEvent`,
`StateChangeEvent`, composable wrappers, activity loggers) is fully implemented.
The following tracks what has been closed and what remains.

---

## Closed gaps

### ~~1. No handler DB session utility~~
`get_session()` in `core/database.py` is exactly what handlers need — it opens an
`AsyncSession`, commits on exit, and rolls back on exception. `RollupSubtaskHandler`
uses it directly. No new utility was required.

### ~~2. `EventBus` not wired into the FastAPI lifespan~~
`api/api/main.py` creates the `EventBus`, attaches it to `app.state.bus`, and calls
`drain_pending()` on shutdown. `api/deps.py` already had all the dep factories — they
now work.

### ~~3. `EventBus` missing from `WorkerContext`~~
`event_bus: EventBus` added to `WorkerContext` (`worker/context.py`), created from
the running loop in `build()`, and drained before Redis connections close in `shutdown()`.

### ~~4. No handler registration~~
`RollupSubtaskHandler` is registered against `TaskUpdatedEvent` in `worker/startup.py`.
The registration block exists and is ready to grow as new handlers are added.

### ~~5. Redis subscriber was a raw asyncio task — not decoupled~~
`subscriber.py` contained a raw `run_task_subscriber()` loop with bidding and social
memory logic embedded inline. Its lifecycle was managed manually via
`asyncio.create_task()` and a raw cancel in `startup.py`.

**What was done:**

- `TaskStreamSubscriber(ExternalEventSubscriber)` in `worker/subscriber.py` replaces
  the raw function. Its only job is to consume from `RedisBus`, deserialise payloads
  via `_parse_stream_event()`, and fire typed stream events onto the in-process `EventBus`.
  No business logic.

- Two stream event types added to `core/eventing/events/stream_events.py`:
  `TaskCreatedStreamEvent` and `TaskCompletedStreamEvent`. These carry only the
  coordination-relevant fields available in the Redis wire format — distinct from the
  in-process `TaskCreatedEvent` which carries a full ORM snapshot.

- Business logic moved into proper `EventHandler` implementations:
  - `worker/handlers/bidding.py` — `TaskBiddingHandler(EventHandler[TaskCreatedStreamEvent])`
  - `worker/handlers/social_memory.py` — `SocialMemoryHandler(EventHandler[TaskCompletedStreamEvent])`

- `worker/startup.py` now registers all three handler types, registers the subscriber
  via `event_bus.subscribe()`, and calls `event_bus.start_subscribers()` /
  `event_bus.stop_subscribers()` — the manual task tracking in `ctx` is gone.

---

## Open gaps

### 1. No audit log handler

**Gap:** The bus is wired and handlers exist for rollup, bidding, and social memory, but
audit logging — writing a record to the DB for every task/agent create, update, and
delete — is not implemented. This is the most immediately useful addition and was the
original motivating example in this document.

**What is needed:** An `AuditLogHandler` per domain area, following the same pattern
as `RollupSubtaskHandler`:

```python
class TaskAuditLogHandler(EventHandler[TaskCreatedEvent]):
    async def handle(self, event: TaskCreatedEvent) -> None:
        async with get_session() as session:
            session.add(AuditLogEntry(
                workspace_id=event.workspace_id,
                entity_type="task",
                entity_id=event.state.id,
                action="created",
                snapshot=dataclasses.asdict(event.state),
            ))
```

This requires an `audit_log` table and model to exist first. That table does not
currently exist.

Registration in `worker/startup.py`:
```python
wctx.event_bus.bind(TaskCreatedEvent, TaskAuditLogHandler())
wctx.event_bus.bind(TaskUpdatedEvent, TaskAuditLogHandler())
```

Registration in `api/api/main.py` lifespan:
```python
bus.bind(TaskCreatedEvent, TaskAuditLogHandler())
bus.bind(TaskUpdatedEvent, TaskAuditLogHandler())
```

Both processes need audit handlers — the API creates and deletes entities; the worker
updates them. Each process has its own `EventBus` instance.

---

### ~~2. API does not publish `task.created` to Redis Streams~~

**What was done:** `api/handlers/task_bridge.py` — `TaskCreatedRedisPublisher` registered
on the in-process `EventBus`. `RedisBus` added to the FastAPI lifespan and stored on
`app.state.redis_bus`. Shutdown block closes the bus.

---

### 3. No tests

**Gap:** No tests exist for `EventBus` dispatch, composable wrappers, activity loggers,
`Snapshot.from_domain`, `TaskStreamSubscriber`, `TaskBiddingHandler`,
`SocialMemoryHandler`, `TaskContext`, or `RollupSubtaskHandler`.

**What is needed (priority order):**

| Test file | What it covers |
|---|---|
| `test_event_bus.py` | `bind`, MRO routing, `apublish` fire-and-forget, `drain_pending`, `start/stop_subscribers` |
| `test_stream_subscriber.py` | `_parse_stream_event` for each known type, unknown type returns None, `TaskStreamSubscriber` start/stop lifecycle |
| `test_handlers.py` | `Retry` backoff, `Filtering` predicate, `Timeout` cancellation, `SyncToAsync` thread dispatch |
| `test_activity_loggers.py` | `TaskActivityLogger.created/updated/deleted` publish correct events; `AsyncMock` as publish callable |
| `test_snapshots.py` | `from_domain` for flat fields, nested snapshots, `tuple[Snapshot, ...]` collections, nullable snapshot fields |
| `test_bidding_handler.py` | Agent scoring, threshold filtering, reservation attempt, `execute_task` enqueue, no-agents path |
| `test_social_memory_handler.py` | Peer query, `store_social` fan-out, single peer failure does not block others |
| `test_task_context.py` | `TaskContext.from_task()`, `MAX_DELEGATION_DEPTH` constant, depth guard override in `execute_task` |
| `test_rollup_handler.py` | Sibling query, all-terminal trigger, partial failure (parent → `"failed"`), concurrent race guard, coordinator credit EMA, reflect job enqueue, no-coordinator path |

`test_rollup_handler.py` and `test_bidding_handler.py` are the highest priority — they
cover the most complex logic with the most edge cases.

`InMemoryBus` (`core/eventing/bus/in_memory_bus.py`) is the test double for `RedisBus`.
Use it in place of a real Redis connection for `TaskStreamSubscriber` and handler tests.

---

## Summary

| Gap | Status |
|-----|--------|
| Handler DB session utility | ✅ Closed — `get_session()` already existed |
| FastAPI lifespan wiring | ✅ Closed — `api/api/main.py` |
| `EventBus` in `WorkerContext` | ✅ Closed — `worker/context.py` |
| Handler registration | ✅ Closed — rollup, bidding, social memory all registered |
| Redis subscriber decoupled via `ExternalEventSubscriber` | ✅ Closed — `TaskStreamSubscriber` + stream event types |
| Audit log handler | ⚠️ Open — `audit_log` table does not exist yet |
| API publishes `task.created` to Redis | ✅ Closed — `TaskCreatedRedisPublisher` in `api/handlers/task_bridge.py` |
| Tests | ❌ Open — nothing tested yet |
