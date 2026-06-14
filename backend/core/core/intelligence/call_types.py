from __future__ import annotations

from enum import StrEnum


class CallType(StrEnum):
    EVALUATE = "evaluate"
    REFLECT = "reflect"
    DECOMPOSE = "decompose"
    ENRICH = "enrich"
    CURATE_MEMORY = "curate_memory"
    EXECUTE = "execute"
