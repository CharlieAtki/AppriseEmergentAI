from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime
from typing import Any, Generic, Self, TypeVar

T = TypeVar("T", bound="Snapshot")


def _map_fields(cls: type, model: Any) -> dict[str, Any]:
    # Reads only already-loaded attributes — no lazy queries triggered here.
    # Override from_domain on the concrete snapshot when field names diverge.
    return {f.name: getattr(model, f.name) for f in dataclasses.fields(cls)}


@dataclasses.dataclass(frozen=True, kw_only=True)
class Snapshot:
    @classmethod
    def from_domain(cls, model: Any) -> Self:
        return cls(**_map_fields(cls, model))


@dataclasses.dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)
    timestamp: datetime = dataclasses.field(default_factory=lambda: datetime.now(UTC))


@dataclasses.dataclass(frozen=True, kw_only=True)
class StateActionEvent(DomainEvent, Generic[T]):
    state: T


@dataclasses.dataclass(frozen=True, kw_only=True)
class StateChangeEvent(StateActionEvent[T]):
    before: T

    @property
    def after(self) -> T:
        return self.state

    @property
    def changes(self) -> frozenset[str]:
        return frozenset(
            f.name
            for f in dataclasses.fields(self.before)  # type: ignore[arg-type]
            if getattr(self.before, f.name) != getattr(self.after, f.name)
        )

    def changed(self, field: str) -> bool:
        return field in self.changes