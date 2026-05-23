# Event Bus — Implementation Gaps

The event bus base layer (`EventBus`, `Snapshot`, `DomainEvent`, `StateActionEvent`,
`StateChangeEvent`, composable wrappers, activity loggers) is fully implemented.
The following gaps remain before the bus is fully operational end-to-end.

---

## Closed gaps

### ~~1. No handler DB session utility~~
`get_session()` in `core/database.py` is exactly what handlers need — it opens an
`AsyncSession`, commits on exit, and rolls back on exception. `RollupSubtaskHandler`
uses it directly. No new utility was required.

### ~~3. `EventBus` not wired into the FastAPI lifespan~~
`api/api/main.py` creates the `EventBus`, attaches it to `app.state.bus`, and calls
`drain_pending()` on shutdown. `api/deps.py` already had all the dep factories — they
now work.

### ~~4. `EventBus` missing from `WorkerContext`~~
`event_bus: EventBus` added to `WorkerContext` (`worker/context.py`), created from
the running loop in `build()`, and drained before Redis connections close in `shutdown()`.

### ~~5. No handler registration~~
`RollupSubtaskHandler` is registered against `TaskUpdatedEvent` in `worker/startup.py`.
The registration block exists and is ready to grow as new handlers are added.

---

## Open gaps

### 1. No audit log handler

**Gap:** The bus is wired and one handler (`RollupSubtaskHandler`) is registered, but
audit logging — writing a record to the DB for every task/agent create, update, and
delete — is not implemented. This is the most immediately useful second handler and
was the original motivating example in this document.

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

### 2. No tests

**Gap:** No tests exist for `EventBus` dispatch, composable wrappers, activity loggers,
`Snapshot.from_domain`, `TaskContext`, or `RollupSubtaskHandler`.

**What is needed (priority order):**

| Test file | What it covers |
|---|---|
| `test_event_bus.py` | `bind`, MRO routing, `apublish` fire-and-forget, `drain_pending` |
| `test_handlers.py` | `Retry` backoff, `Filtering` predicate, `Timeout` cancellation, `SyncToAsync` thread dispatch |
| `test_activity_loggers.py` | `TaskActivityLogger.created/updated/deleted` publish correct events; `AsyncMock` as publish callable |
| `test_snapshots.py` | `from_domain` for flat fields, nested snapshots, `tuple[Snapshot, ...]` collections, nullable snapshot fields; provenance fields (`coordinator_agent_id`, `created_by_agent_id`, `delegation_depth`) |
| `test_task_context.py` | `TaskContext.from_task()`, `MAX_DELEGATION_DEPTH` constant, depth guard override in `execute_task` |
| `test_rollup_handler.py` | Sibling query, all-terminal trigger, partial failure (parent → `"failed"`), concurrent race guard (parent already terminal), coordinator credit EMA, reflect job enqueue, no-coordinator path |

`test_rollup_handler.py` is the highest priority — it covers the most complex new
logic with the most edge cases.

---

## Summary

| Gap | Status |
|-----|--------|
| Handler DB session utility | ✅ Closed — `get_session()` already existed |
| Concrete handlers | ⚠️ Partial — `RollupSubtaskHandler` exists; audit log handler still needed |
| FastAPI lifespan wiring | ✅ Closed — `api/api/main.py` |
| `EventBus` in `WorkerContext` | ✅ Closed — `worker/context.py` |
| Handler registration | ✅ Closed — `worker/startup.py` (rollup); API handlers pending |
| Tests | ❌ Open — nothing tested yet |
