from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MemoryTier = Literal["episodic", "procedural", "social"]
SupersessionVerdict = Literal["supersedes", "complements", "contradicts"]


@dataclass(frozen=True)
class MemoryItem:
    tier: MemoryTier
    id: str
    score: float
    text: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ProceduralRule:
    """Typed view of a procedural MemoryItem parsed at the memory boundary.

    Replaces raw payload dict-access in callers — the single ``from_item``
    classmethod owns all Qdrant payload key names.
    """

    id: str
    text: str
    domain: str
    last_accessed_at: str

    @classmethod
    def from_item(cls, item: MemoryItem) -> ProceduralRule:
        return cls(
            id=item.id,
            text=item.text,
            domain=item.payload.get("domain", ""),
            last_accessed_at=item.payload.get("last_accessed_at", "unknown"),
        )


@dataclass
class MemoryContext:
    episodes: list[MemoryItem] = field(default_factory=list)
    procedures: list[MemoryItem] = field(default_factory=list)
    social: list[MemoryItem] = field(default_factory=list)
