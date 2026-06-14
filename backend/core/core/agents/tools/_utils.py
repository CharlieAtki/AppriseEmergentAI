from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory.types import MemoryItem


def _format_memory_items(items: list[MemoryItem]) -> str:
    return "\n\n".join(f"[relevance {item.score:.2f}] {item.text}" for item in items)
