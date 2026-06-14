from __future__ import annotations

from enum import Enum


class CallType(str, Enum):
    EVALUATE = "evaluate"
    REFLECT = "reflect"
    DECOMPOSE = "decompose"
    ENRICH = "enrich"
    CURATE_MEMORY = "curate_memory"
    EXECUTE = "execute"
