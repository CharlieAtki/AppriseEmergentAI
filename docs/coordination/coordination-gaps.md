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

## Open gaps

### 1. CFP path is dead — no subscriber consumes `cfp.{workspace_id}.issued`

**Gap:** `issue_cfp()` publishes a `CfpIssuedStreamEvent` to `cfp.{workspace_id}.issued`.
No handler or subscriber reads this stream.

When an agent decides `"cfp"` in `execute_task`, `_release_to_pool` correctly returns
the task to `"open"` and re-publishes via `stream_logger.task_created(task)` so standard
bidding picks it up. `issue_cfp()` fires before that — its event goes unconsumed.

**Impact:** The structured ContractNet negotiation round (broadcast CFP → agents bid →
winner selected) never happens. Tasks delegated via CFP fall back silently to whoever
wins the standard `stream:task` bid.

**What is needed:**

Option A — remove `issue_cfp()` and treat CFP as standard re-bidding (current de facto
behaviour). Delete `CfpIssuedStreamEvent`, `cfp_issued` from `TaskStreamLogger`, and
`issue_cfp` from `contract_net.py`.

Option B — implement a CFP subscriber. `CfpIssuedStreamEvent` already exists with all
fields. What remains:

```python
# worker/handlers/cfp.py
@dataclasses.dataclass
class CfpHandler(EventHandler[CfpIssuedStreamEvent]):
    redis: Redis
    arq_queue: ArqRedis

    async def handle(self, event: CfpIssuedStreamEvent) -> None:
        # Collect bids, select winner, enqueue execute_task for winner.
        ...
```

- A dedicated `CfpStreamSubscriber` (or extend `TaskStreamSubscriber`) that reads
  `cfp.{workspace_id}.issued` — this stream key is workspace-specific and cannot be
  handled by the current single-stream subscriber without changes.
- Add `"cfp.issued": CfpIssuedStreamEvent` to `_REGISTRY` in `subscriber.py`.
- Register `CfpHandler` in `worker/startup.py`.

Decide which option is correct before implementing anything else in the CFP path.

---

## Summary

| Gap | Status |
|-----|--------|
| `difficulty` dropped from `TaskCreatedStreamEvent` | ✅ Closed |
| Raw stream payloads constructed inline — `TaskStreamLogger` missing | ✅ Closed |
| Stream events untyped end-to-end — `StreamEvent` base class missing | ✅ Closed |
| CFP subscriber missing — `cfp.{workspace_id}.issued` unconsumed | ❌ Open |