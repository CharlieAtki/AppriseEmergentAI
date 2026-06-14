from __future__ import annotations

import logging
from dataclasses import dataclass

from core.intelligence.llm_router import LLMRouter
from core.intelligence.reflection.pipeline import PipelineStage
from core.intelligence.reflection.types import PipelineResult, ReflectContext
from core.memory.agent_memory import AgentMemory
from worker.reflection.stages import _stage_episodic, _stage_reflect, _stage_rules, _stage_skills

logger = logging.getLogger(__name__)

# Execution order matters: reflect must run before skills (skill_domains) and rules
# (result.rule). episodic runs last — it writes the factual execution record from
# rctx, independently of the other stages. Both rules and episodic share the same
# full_reflect gate so stages_run accurately reflects what actually executed.
REFLECT_PIPELINE: tuple[PipelineStage, ...] = (
    PipelineStage("reflect", fn=_stage_reflect),
    PipelineStage("skills", fn=_stage_skills),
    PipelineStage("rules", fn=_stage_rules, gate=lambda ctx: ctx.full_reflect),
    PipelineStage("episodic", fn=_stage_episodic, gate=lambda ctx: ctx.full_reflect),
)


@dataclass(frozen=True)
class ReflectionManager:
    """Sequences the reflection pipeline stages. Owns LLMRouter and AgentMemory.

    Constructed once at worker startup and held in WorkerContext. Reused across all jobs.
    Per-stage exceptions are caught and logged — a failing stage does not abort the pipeline.
    """

    pipeline: tuple[PipelineStage, ...]
    llm_router: LLMRouter
    memory: AgentMemory

    async def run(self, rctx: ReflectContext) -> PipelineResult:
        """Execute the pipeline stages in order, accumulating outputs into PipelineResult.

        Each stage receives the same ``rctx`` (immutable) and the same ``result``
        accumulator (mutable). Stages access the active ``JobSpan`` via
        ``current_span()`` — no span argument is threaded through the call stack.

        A stage that fails is logged and skipped — the pipeline continues with
        whatever partial result has been built so far. Stage names are appended to
        ``result.stages_run`` on success and ``result.stages_failed`` on exception.
        """
        result = PipelineResult()
        for stage in self.pipeline:
            if stage.gate is not None and not stage.gate(rctx):
                continue
            try:
                result = await stage.fn(rctx, result, self.llm_router, self.memory)
                result.stages_run.append(stage.name)
            except Exception:
                logger.exception(
                    "reflect stage=%s failed — continuing with partial result", stage.name
                )
                result.stages_failed.append(stage.name)
        return result
