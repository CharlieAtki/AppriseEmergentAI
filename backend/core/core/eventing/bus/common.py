from __future__ import annotations

import abc
import types
import uuid
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from typing import Self, Union, get_args, get_origin, get_type_hints


@dataclass
class DomainEvent(abc.ABC):  # noqa: B024
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class StreamEvent(DomainEvent):
    """Base class for cross-process events published to Redis Streams.

    Extends DomainEvent with the Redis transport contract. Subclasses must
    implement all four members — the base raises NotImplementedError so that
    a partially-implemented subclass fails loudly at the call site rather than
    silently publishing a malformed payload.

    stream_key  — the Redis stream name to XADD to. Implemented as a property
                  (not a ClassVar) so a subclass can vary it per-instance if a
                  future event type needs to; today's subclasses (task, cfp)
                  all return a static, non-workspace-scoped key. Redis consumer
                  groups (see worker/startup.py) already deliver each message to
                  exactly one worker — there is no fan-out across workers to
                  de-duplicate, so a single shared key per event type is
                  sufficient. ``event.workspace_id`` is only read by the handler
                  that claims the message, to scope its own DB query (e.g. which
                  agents belong to that workspace) — it does not route or filter
                  the message itself.

    event_type  — discriminator string written into every payload so the subscriber
                  can route to the correct ``from_payload`` without knowing the
                  Python class. Must be unique across all StreamEvent subclasses.

    to_payload  — returns the full dict that is JSON-serialised onto the stream.
                  Must include ``event_type``. UUID fields must be str-cast.
                  ``event_id`` and ``timestamp`` should be included for
                  deduplication and debugging.

    from_payload — reconstructs an instance from the parsed Redis dict. Called by
                  ``_parse_stream_event`` in worker/subscriber.py. Must handle
                  missing optional fields with sensible defaults so that messages
                  published before a field was added are not fatal.

    Invariant: ``from_payload(event.to_payload())`` must round-trip losslessly for
    all required fields. Optional fields may coerce None on the way back.
    """

    @property
    def stream_key(self) -> str:
        raise NotImplementedError

    @property
    def event_type(self) -> str:
        raise NotImplementedError

    def to_payload(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_payload(cls, payload: dict) -> StreamEvent:
        raise NotImplementedError


@dataclass(frozen=True, kw_only=True)
class Snapshot:
    """Immutable point-in-time view of an entity, used as the payload of a
    :class:`StateActionEvent` or :class:`StateChangeEvent`.

    Concrete subclasses capture only the fields relevant to event consumers::

        @dataclass(frozen=True, kw_only=True)
        class AgentSnapshot(Snapshot):
            id: uuid.UUID
            workspace_id: uuid.UUID
            name: str
            skills: dict | None

    The default :meth:`from_domain` constructs the snapshot by matching field
    names directly to attributes on the domain object. It handles three cases:

    - **Primitive and scalar values** are copied directly.
    - **Collections** — fields declared as ``tuple[T, ...]`` accept any
      iterable from the domain object and materialise it as a tuple. If ``T``
      is a :class:`Snapshot` subclass, ``from_domain`` is called on each
      element; scalar element types are copied directly.
    - **Nested snapshots** — fields declared as a :class:`Snapshot` subclass
      (or ``SnapshotSubclass | None``) are constructed recursively via
      ``from_domain``.

    Override :meth:`from_domain` when field names on the snapshot differ from
    those on the domain object, or when a value requires a transformation not
    covered above.
    """

    @classmethod
    def from_domain(cls, model: object) -> Self:
        """Construct a snapshot from a domain object by matching field names.

        Covers the full inheritance chain — fields defined on a base snapshot
        class are included alongside those on the subclass. Override when a
        field name differs from the domain attribute, or when a value requires
        transformation beyond a direct field-name mapping.
        """
        hints = get_type_hints(cls)
        kwargs: dict[str, object] = {}
        for f in fields(cls):
            value = getattr(model, f.name)
            hint = hints.get(f.name)
            snapshot_cls, allows_none = _unwrap_snapshot_type(hint)
            if snapshot_cls is not None:
                kwargs[f.name] = (
                    None if (value is None and allows_none) else snapshot_cls.from_domain(value)
                )
                continue
            tuple_snapshot_cls = _unwrap_tuple_snapshot_type(hint)
            if tuple_snapshot_cls is not None:
                kwargs[f.name] = tuple(tuple_snapshot_cls.from_domain(v) for v in value)
                continue
            if get_origin(hint) is tuple:
                kwargs[f.name] = tuple(value)
                continue
            kwargs[f.name] = value
        return cls(**kwargs)


def _unwrap_snapshot_type(hint: object) -> tuple[type[Snapshot] | None, bool]:
    """Return (snapshot_cls, allows_none) when hint is or wraps a Snapshot subclass."""
    if isinstance(hint, type) and issubclass(hint, Snapshot):
        return hint, False
    origin = get_origin(hint)
    if origin is Union or origin is types.UnionType:
        snapshot_cls: type[Snapshot] | None = None
        allows_none = False
        for arg in get_args(hint):
            if arg is type(None):
                allows_none = True
            elif isinstance(arg, type) and issubclass(arg, Snapshot):
                snapshot_cls = arg
        if snapshot_cls is not None:
            return snapshot_cls, allows_none
    return None, False


def _unwrap_tuple_snapshot_type(hint: object) -> type[Snapshot] | None:
    """Return the element Snapshot subclass for a hint of the form tuple[SnapshotSubclass, ...]."""
    if get_origin(hint) is tuple:
        args = get_args(hint)
        if (
            len(args) == 2
            and args[1] is Ellipsis
            and isinstance(args[0], type)
            and issubclass(args[0], Snapshot)
        ):
            return args[0]
    return None


@dataclass(kw_only=True)
class StateActionEvent[T: Snapshot](DomainEvent):
    """A domain event that carries the resulting state of a CUD operation.

    ``state`` is an immutable :class:`Snapshot` captured at emission time.
    For creation events it is the initial state; for deletion events it is the
    final state before removal; for updates, prefer :class:`StateChangeEvent`
    which additionally records the prior state.

    Can be mixed in alongside a domain-specific event base class::

        @dataclass(kw_only=True)
        class AgentEvent(DomainEvent):
            workspace_id: uuid.UUID

        @dataclass(kw_only=True)
        class AgentCreatedEvent(AgentEvent, StateActionEvent[AgentSnapshot]):
            pass
    """

    state: T


@dataclass(kw_only=True)
class StateChangeEvent[T: Snapshot](StateActionEvent[T]):
    """A domain event that records an entity transitioning from one state to another.

    Extends :class:`StateActionEvent` with ``before`` — the entity state prior
    to the operation. ``after`` is a read-only alias for ``state``.

    Construct with ``before`` and ``state`` (the resulting state)::

        AgentUpdatedEvent(workspace_id=..., before=old_snapshot, state=new_snapshot)
    """

    before: T

    @property
    def after(self) -> T:
        """The resulting state — alias for ``state``."""
        return self.state

    @property
    def changes(self) -> frozenset[str]:
        """Names of snapshot fields whose value differs between before and after."""
        return frozenset(
            f.name
            for f in fields(self.before)
            if getattr(self.before, f.name) != getattr(self.after, f.name)
        )

    def changed(self, field_name: str) -> bool:
        """Return True if *field_name* has a different value in before vs after."""
        return bool(getattr(self.before, field_name) != getattr(self.after, field_name))
