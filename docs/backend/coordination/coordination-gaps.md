# Coordination — Implementation Gaps

The ContractNet bidding layer (`compute_bid_score`, `attempt_reservation`, `decompose_and_publish`,
`TaskStateMachine`) is implemented. The following tracks what has been closed and what remains.

---

## Closed gaps

### ~~1. `difficulty` dropped from `TaskCreatedStreamEvent`~~

`decompose_and_publish()` published `difficulty` in the `stream:task` payload but
`TaskCreatedStreamEvent` did not declare the field and `_parse_stream_event()` did not
parse it — the value was silently dropped on every subtask creation event.

**What was done:** `difficulty: float | None = None` added to `TaskCreatedStreamEvent`
(`core/eventing/events/stream_events.py`). `_parse_stream_event()` now parses it from
the payload (`worker/subscriber.py`).

---

### ~~2. Raw stream payload dicts constructed inline at every publish site~~

Cross-process stream publishing used hand-crafted dicts at four separate sites
(`decompose.py`, `contract_net.py`, `execute_task.py` ×2). Payload shape drifted between
sites — `_release_to_pool` was missing `difficulty` and `task_type`, and `decompose.py`
published three fields (`organisation_id`, `parent_task_id`, `decomposed_by_agent_id`)
that no consumer parsed. The `BusProtocol` was also imported outside `TYPE_CHECKING` in
`decompose.py`.

**What was done (phase 1 — TaskStreamLogger):**

- `StreamPublishFn = Callable[[str, dict], Awaitable[None]]` added to
  `core/eventing/activity/base.py` as the cross-process equivalent of `PublishFn`.
- `TaskStreamLogger` created in `core/eventing/activity/task_stream_logger.py` — owns
  all payload construction for `task.created`, `task.completed`, and `cfp_issued`.
  Mirrors `TaskActivityLogger` exactly: receives `StreamPublishFn` at construction,
  callers never touch the bus or construct dicts directly.
- `decompose_and_publish()` signature changed: `bus: BusProtocol` → `stream_logger:
  TaskStreamLogger`. Unparsed fields removed from payload. `BusProtocol` import removed.
- `issue_cfp()` signature changed: `bus: BusProtocol` → `stream_logger:
  TaskStreamLogger`. Body reduced to a single `await stream_logger.cfp_issued(...)` call.
- `execute_task.py`: `stream_logger` constructed alongside `task_logger`. All three
  inline publish sites replaced with logger calls. `_release_to_pool` signature
  simplified (dropped `task_id`/`workspace_id` string args, fixing the reservation key).

---

### ~~3. Stream events untyped end-to-end — `StreamEvent` base class missing~~

After phase 1, `TaskStreamLogger` eliminated raw dict construction at call sites but
the underlying wire format was still untyped: `StreamPublishFn = Callable[[str, dict], ...]`,
`RedisBus.publish(stream, dict)`, and `_parse_stream_event` still hand-coded UUID/float
coercions. Producer and deserialiser still had to be kept in sync manually. Two fields
(`organisation_id`, `task_type`) were in the published payload but absent from
`TaskCreatedStreamEvent`, silently dropped on arrival. `CfpIssuedStreamEvent` did not exist.

**What was done (phase 2 — StreamEvent base):**

- `StreamEvent(DomainEvent)` base class added to `core/eventing/bus/common.py`. Defines
  the contract every cross-process event must implement: `stream_key` property, `event_type`
  property, `to_payload() -> dict`, `@classmethod from_payload(cls, payload) -> Self`.
  `stream_key` is a property (not a ClassVar) because CFP keys embed `workspace_id` at
  runtime and cannot be a static string.
- `stream_events.py` rewritten: `TaskCreatedStreamEvent`, `TaskCompletedStreamEvent`, and
  new `CfpIssuedStreamEvent` each implement all four members. `TaskCreatedStreamEvent`
  gains `organisation_id: uuid.UUID` and `task_type: str | None` (previously published
  but not on the class). Each class is now the single source of truth for its wire format.
- `RedisBus.apublish(event: StreamEvent)` added. Uses `event.stream_key` for routing and
  `event.to_payload()` for serialization. Old `publish(str, dict)` retained only for
  `sample_metrics.py` which publishes to `stream:workspace` (no `StreamEvent` yet).
- `StreamPublishFn` updated to `Callable[[StreamEvent], Awaitable[None]]`.
- `TaskStreamLogger` updated to construct typed `StreamEvent` instances instead of dicts.
  Wrong field type now raises `TypeError` at construction, not silently at the consumer.
- `_parse_stream_event` in `subscriber.py` replaced with a registry lookup:
  `_REGISTRY: dict[str, type[StreamEvent]]` maps `event_type` string → class.
  Deserialization calls `cls.from_payload(payload)`. Adding a new event type = define
  the class + one line in `_REGISTRY`. No other files change.
- `execute_task.py` updated: `TaskStreamLogger(wctx.bus.apublish)`.

---

## Closed gaps (continued)

### ~~4. CFP path was dead — no subscriber, no influence credit~~

**Gap:** `issue_cfp()` published a `CfpIssuedStreamEvent` that no subscriber read.
`task.coordinator_agent_id` was never set on CFP release, so the initiating agent
received zero influence credit when the re-bid task completed.

**What was done:**

- `CfpIssuedStreamEvent.stream_key` changed from `f"cfp.{workspace_id}.issued"` to
  `"stream:cfp"`, matching the `stream:task` convention. Workspace isolation is enforced
  by the SETNX key and handler-level filtering, not the stream key. This eliminates the
  need for workspace-list queries at startup and keeps the subscriber pattern identical to
  `TaskStreamSubscriber`.

- `_release_to_pool()` in `execute_task.py` now sets `task.coordinator_agent_id =
  execution.agent_id` before transitioning the task to `"open"`. This is the single wire
  that connects the CFP path to the existing `CoordinatorInfluenceHandler`.

- `CoordinatorInfluenceHandler` extended to handle two delegation paths:
  - **Decompose** (task has subtasks): quality signal = avg subtask quality (unchanged)
  - **CFP** (no subtasks, direct completion): quality signal = `quality_score ×
    CFP_COORDINATOR_CREDIT` (default 0.5). Partial credit because the coordinator routed
    the task but did not structure or execute it.

- `CfpHandler` added (`worker/handlers/cfp.py`): fired by `CfpIssuedStreamEvent`, excludes
  the initiating agent, scores remaining active agents with `compute_bid_score()`, and
  calls `attempt_reservation()` for the highest scorer. Falls through silently if no
  agent qualifies — the `TaskCreatedStreamEvent` from `_release_to_pool()` acts as
  the safety fallback via `TaskBiddingHandler`.

- `CfpStreamSubscriber` added (`worker/subscriber.py`): reads `stream:cfp` via consumer
  group `"cfp-group"`, deserializes via `_CFP_REGISTRY`, dispatches to `event_bus`. Reuses
  `_parse_stream_event()` with the CFP registry passed explicitly.

- `CfpHandler` and `CfpStreamSubscriber` registered in `worker/startup.py`.

- `CFP_COORDINATOR_CREDIT: float = 0.5` added to `core/config/__init__.py`.

**Race condition accepted:** `CfpHandler` (excludes initiating agent) and
`TaskBiddingHandler` (fallback, includes all agents) both race via SETNX on the same
task. SETNX guarantees exactly one winner. The initiating agent's low skill score makes
re-winning unlikely; if it does occur, the task re-enters the CFP path with the same
coordinator tracked.

---

---

### ~~5. Coordinator credit misattribution — three bugs in `_credit_coordinator()`~~

**Gap:** The original `_credit_coordinator()` heuristic used subtask presence *at event time* to
distinguish the decompose path from the CFP path. This was wrong in three ways:

- **Bug A (pure decompose):** The parent task goes to `"completed"` immediately after
  `_finalise_execution` — before any subtask executes. At that moment, 0 subtasks are `"completed"`.
  The query returns empty. The decomposing agent received zero credit despite having structured the work.

- **Bug B (CFP → Decompose):** Same timing problem. Agent A (CFP) and Agent B (decompose) both
  received zero credit because the quality signal from subtasks did not exist at parent-completion time.

- **Bug C (spurious per-subtask credit):** Subtasks inherit `coordinator_agent_id` from
  `decompose.py:73`. When each subtask self-executed and completed, `_credit_coordinator()` saw a
  `coordinator_agent_id`, found no sub-subtasks, fell through to the CFP formula, and gave the
  decomposer `quality × 0.5` credit per subtask. Three subtasks = three CFP-style partial credits
  instead of one full credit at avg quality.

**What was done:**

- `execution_path TEXT NULL` column added to `task_executions`. Written atomically with
  `status="completed"` at every coordination point in `execute_task.py`: `"self_execute"` (Phase 6),
  `"decompose"` (`_finalise_execution()`), `"cfp"` (`_release_to_pool()`).

- Alembic migration `004_add_execution_path_to_task_executions.py` added.

- `compute_delegation_credits(task_id, workspace_id, quality, session)` module-level helper added
  to `worker/handlers/agent_credit.py`. Queries `TaskExecution WHERE task_id=X AND
  execution_path IN ("cfp","decompose") AND status="completed"`. Returns
  `list[(agent_id, quality_signal)]`. One DB round-trip regardless of chain depth.

- `AgentCreditHandler._credit_coordinator()` rewritten. Dispatches on `parent_task_id`:
  - Root task: call `compute_delegation_credits()` directly with `event.state.quality_score`.
  - Subtask: call `_subtask_rollup_credits()` — checks if all siblings are terminal (last sibling
    gate), computes avg quality across completed sibling executions, then calls
    `compute_delegation_credits()` on the **parent** task's execution chain.

- `InfluenceUpdateHandler` and `CoordinatorInfluenceHandler` deleted. Replaced by the single
  `AgentCreditHandler` that handles both executor and coordinator credit in one DB session.

See `docs/eventing/task-provenance-and-rollup.md` — "The `execution_path` audit trail" and
"The four coordination scenarios end-to-end" for the full flow with traces.

---

## Summary

| Gap | Status |
|-----|--------|
| `difficulty` dropped from `TaskCreatedStreamEvent` | ✅ Closed |
| Raw stream payloads constructed inline — `TaskStreamLogger` missing | ✅ Closed |
| Stream events untyped end-to-end — `StreamEvent` base class missing | ✅ Closed |
| CFP subscriber missing — initiating agent received no influence credit | ✅ Closed |
| Coordinator credit misattribution — three bugs in `_credit_coordinator()` | ✅ Closed |