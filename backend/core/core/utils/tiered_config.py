from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def merge_tiers(*sources: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge N optional override mappings, later sources winning per key.

    A missing key (source is None or {}) means "inherit from an earlier tier" —
    it never means "reset to empty". Used to layer platform/org/workspace
    config tiers without duplicating the merge order in every resolver.
    """
    merged: dict[str, Any] = {}
    for source in sources:
        if source:
            merged.update(source)
    return merged
