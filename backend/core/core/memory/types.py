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


@dataclass
class MemoryContext:
    episodes: list[MemoryItem] = field(default_factory=list)
    procedures: list[MemoryItem] = field(default_factory=list)
    social: list[MemoryItem] = field(default_factory=list)
