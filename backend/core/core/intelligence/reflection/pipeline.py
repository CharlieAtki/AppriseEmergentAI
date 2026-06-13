from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from core.intelligence.reflection.types import PipelineResult, ReflectContext


@dataclass(frozen=True)
class PipelineStage:
    """Declarative entry for one stage in the reflection pipeline.

    Analogous to a graph edge in the cascade pattern — defines what runs and
    under what condition, without owning any execution logic itself.

    Fields:
        name: Stage identifier used in ``PipelineResult.stages_run/stages_failed``
              and log output. Must be unique within a pipeline.
        fn:   Async stage function with signature
              ``(rctx, result, llm, memory, span) -> PipelineResult``.
              All stages share this signature even if they do not use every dep,
              allowing ``ReflectionManager.run()`` to call them uniformly.
        gate: Optional predicate evaluated against ``ReflectContext`` before the
              stage runs. If it returns False the stage is skipped entirely —
              not counted as failed. Use for opt-in stages like rule extraction
              that only make sense for non-trivial executions.
    """

    name: str
    fn:   Callable[..., Awaitable[PipelineResult]]
    gate: Callable[[ReflectContext], bool] | None = None