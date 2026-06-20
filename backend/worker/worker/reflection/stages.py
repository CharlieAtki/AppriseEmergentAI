from __future__ import annotations

import logging

from core.coordination.skills import apply_skill_delta, compute_delta_magnitude
from core.intelligence.call_types import CallType
from core.intelligence.llm_router import LLMRouter
from core.intelligence.prompts.reflection import reflect as reflect_prompt
from core.intelligence.prompts.reflection.reflect import ExistingRule, ResultContext, TaskContext
from core.intelligence.reflection.types import PipelineResult, ReflectContext
from core.memory.agent_memory import AgentMemory
from core.memory.types import ProceduralRule
from core.repositories.agent_repository import AgentRepository
from core.repositories.procedural_knowledge_repository import ProceduralKnowledgeRepository
from core.repositories.skill_repository import SkillRepository

from worker.span import current_span

logger = logging.getLogger(__name__)


def _primary_domain(rctx: ReflectContext) -> str:
    """Return the stable domain label for rule storage and retrieval.

    Uses task_type (a dedicated TEXT column) rather than domain_tags JSONB keys,
    whose order Postgres normalises alphabetically — not the task creator's intent.
    domain_tags is used only for multi-domain retrieval in _stage_reflect.
    """
    return rctx.task_type or "general"


async def _stage_reflect(
    rctx: ReflectContext,
    result: PipelineResult,
    llm: LLMRouter,
    memory: AgentMemory,
) -> PipelineResult:
    """Stage 1 — unified LLM reflection (CallType.REFLECT).

    Lightweight path (``not rctx.full_reflect``): classifies which skills from the
    required skill set were exercised and suggests new skills to seed. One call,
    short prompt, no rule extraction.

    Full path (``rctx.full_reflect``): additionally loads existing procedural rules
    from Qdrant across ``domain_tags`` keys (deduplicated by point ID), then asks
    for a generalised rule with a supersession verdict. The rule is constrained to
    reference a specific tool/pattern/artifact from the trace — generic rules are
    rejected at the prompt level and return None.

    Sets ``result.skill_domains``, ``result.new_skill_suggestions``, ``result.rule``,
    ``result.verdict``, and ``result.superseded_ids`` for downstream stages.
    """
    span = current_span()
    task_ctx = TaskContext(
        title=rctx.task_title,
        description=rctx.task_description,
        task_type=rctx.task_type,
        required_skills=rctx.required_skills,
        difficulty=rctx.difficulty,
    )
    result_ctx = ResultContext(
        summary=rctx.artifact or (rctx.error or {}).get("message", "") or "",
        tool_trace=rctx.tool_trace,
    )

    # Load existing rules only on the full path — needed for supersession decisions.
    # Query each domain_tag separately and deduplicate by point ID so no rule appears twice.
    existing: list[ExistingRule] = []
    if rctx.full_reflect:
        retrieval_domains = (
            list(rctx.domain_tags.keys())
            if rctx.domain_tags
            else ([rctx.task_type] if rctx.task_type else [])
        )
        seen_ids: set[str] = set()
        for d in retrieval_domains:  # full list needed here — retrieve across all tags
            for item in await memory.retrieve_procedures_for_domain(
                str(rctx.agent_id), str(rctx.workspace_id), d
            ):
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    rule = ProceduralRule.from_item(item)
                    existing.append(
                        ExistingRule(
                            id=rule.id,
                            domain=rule.domain,
                            text=rule.text,
                        )
                    )

    raw = await llm.complete(
        reflect_prompt.build_prompt(
            task_ctx,
            result_ctx,
            rctx.heuristic_score,
            status=rctx.status,
            full_reflect=rctx.full_reflect,
            existing_rules=existing if existing else None,
        ),
        CallType.REFLECT,
        json_mode=True,
    )
    output = reflect_prompt.parse(raw)

    result.skill_domains = output.skill_domains
    result.new_skill_suggestions = output.new_skill_suggestions
    result.rule = output.generalised_rule
    result.verdict = output.verdict
    result.superseded_ids = output.superseded_ids if output.superseded_ids else None

    await span.emit(
        "reflect.classified",
        {
            "skill_domains": output.skill_domains,
            "full_reflect": rctx.full_reflect,
            "rule_extracted": output.generalised_rule is not None,
        },
    )
    return result


async def _stage_skills(
    rctx: ReflectContext,
    result: PipelineResult,
    _llm: LLMRouter,
    _memory: AgentMemory,
) -> PipelineResult:
    """Stage 2 — algorithmic skill update (no LLM call).

    Computes delta magnitude for each skill domain identified by ``_stage_reflect``
    using ``compute_delta_magnitude(heuristic_score, current_skill)``, then applies
    logistic growth via ``apply_skill_delta()``.

    Current skill value is read from the live DB row under a ``FOR UPDATE`` lock —
    not from ``rctx.agent_skills`` — because a concurrent reflect job for the same
    agent may have already updated the agent since the snapshot was taken. The lock
    prevents silent overwrite.

    Seeds ``result.new_skill_suggestions`` at 0.1 only for skills absent from
    ``agent.skills`` (key not present — a skill at 0.0 is not overwritten by a seed).

    Idempotency: checks for an existing SkillSnapshot with this execution_id before
    applying any delta. A previous run that completed this stage produced that row —
    skip to prevent double-applying the delta on ARQ retry.

    Skips the DB write entirely if both lists are empty. Writes a ``SkillSnapshot``
    for the observability audit trail when any change is made.
    """
    if not result.skill_domains and not result.new_skill_suggestions:
        return result

    span = current_span()
    async with span.session() as session:
        skill_repo = SkillRepository(session)
        # Idempotency guard — if a SkillSnapshot for this execution already exists,
        # the delta was applied on a previous attempt. Skip to avoid double-counting.
        if await skill_repo.get_by_execution(rctx.execution_id, rctx.agent_id) is not None:
            return result

        # AgentRepository constructed here because stages own their sessions via span.session().
        # get_for_update() acquires a row-level lock to prevent concurrent overwrites between
        # this reflect pipeline and execute_task's skill decay (which runs in a separate job).
        agent_repo = AgentRepository(session)
        agent = await agent_repo.get_for_update(rctx.agent_id)
        if agent is None:
            return result

        current_skills: dict[str, float] = agent.skills or {}
        updated = dict(current_skills)

        for skill_name in result.skill_domains:
            # Guard: only apply deltas to known required skills.
            # Names outside required_skills belong in new_skill_suggestions, not here.
            if skill_name not in rctx.required_skills:
                continue
            current = current_skills.get(skill_name, 0.0)
            delta = compute_delta_magnitude(rctx.heuristic_score, current)
            updated[skill_name] = apply_skill_delta(current, delta)

        filtered_out = [s for s in result.skill_domains if s not in rctx.required_skills]
        if filtered_out:
            logger.warning(
                "reflect _stage_skills: LLM named skills outside required set — dropped=%s execution=%s",
                filtered_out,
                rctx.execution_id,
            )
            await span.emit("skills.filtered", {"dropped": filtered_out})

        for skill_name in result.new_skill_suggestions:
            if skill_name not in updated:
                updated[skill_name] = 0.1

        agent.skills = updated
        await agent_repo.save(agent)
        await skill_repo.record(
            agent_id=agent.id,
            organisation_id=rctx.organisation_id,
            workspace_id=rctx.workspace_id,
            skills=agent.skills,
            execution_id=rctx.execution_id,
        )

    return result


async def _stage_rules(
    rctx: ReflectContext,
    result: PipelineResult,
    _llm: LLMRouter,
    memory: AgentMemory,
) -> PipelineResult:
    """Stage 3 — procedural rule persistence (no LLM call, gated by full_reflect).

    Persists ``result.rule`` (set by ``_stage_reflect``) to Postgres and Qdrant.
    Returns immediately when ``result.rule`` is None — ``_stage_reflect`` may decline
    to extract a rule even on full_reflect executions.

    Three-phase dual-write (Postgres-first durability preserved):
      Phase 1 — Postgres: insert ProceduralKnowledgeLog (audit trail, committed first).
      Phase 2 — Qdrant:   store rule embedding (retrieval index).
      Phase 3 — Postgres: update vector_store_ref to mark both writes complete.

    Idempotency via execution_id:
      - No existing row → first run, execute all three phases.
      - Existing row with vector_store_ref=None → Qdrant previously failed; skip
        Phase 1, retry Phase 2, update Phase 3.
      - Existing row with vector_store_ref set → fully complete, skip everything.
    """
    if not result.rule:
        return result

    span = current_span()
    storage_domain = _primary_domain(rctx)

    # Phase 1: Postgres write — committed before Qdrant is touched.
    # If Qdrant later fails, the audit record is preserved with vector_store_ref=None.
    async with span.session() as session:
        knowledge_repo = ProceduralKnowledgeRepository(session)
        existing_log = await knowledge_repo.get_by_execution(rctx.execution_id)

        if existing_log is not None and existing_log.vector_store_ref is not None:
            return result  # both writes already completed on a previous attempt

        if existing_log is None:
            log_id = await knowledge_repo.record(
                workspace_id=rctx.workspace_id,
                agent_id=rctx.agent_id,
                domain=storage_domain,
                rule_text=result.rule,
                execution_id=rctx.execution_id,
            )
        else:
            log_id = existing_log.id  # Postgres row exists; vector_store_ref=None — redo Qdrant

    # Phase 2: Qdrant write — session already committed above.
    # If this fails, vector_store_ref stays None and the next retry picks up from here.
    point_id = await memory.store_procedure(
        str(rctx.agent_id),
        str(rctx.workspace_id),
        rule=result.rule,
        domain=storage_domain,
        verdict=result.verdict,
        superseded_ids=result.superseded_ids,
    )

    # Phase 3: stamp vector_store_ref — marks both writes as complete for idempotency.
    async with span.session() as session:
        knowledge_repo = ProceduralKnowledgeRepository(session)
        log = await knowledge_repo.get_by_id(log_id)
        if log is not None:
            log.vector_store_ref = point_id
            await knowledge_repo.save(log)

    return result


async def _stage_episodic(
    rctx: ReflectContext,
    result: PipelineResult,
    _llm: LLMRouter,
    memory: AgentMemory,
) -> PipelineResult:
    """Stage 4 — write the factual execution record to episodic memory (no LLM call).

    This is the sole episodic write for a self-execute task. ``execute_task`` owns
    execution; the reflection pipeline owns all memory writes — episodic included.

    Gated on ``rctx.full_reflect`` (difficulty >= 3.0 or step_count > 3) to keep
    trivial completions out of top-k retrieval. Mirrors the text format used
    historically in ``_build_episodic_entry``, reading directly from the frozen
    ``ReflectContext`` rather than live ORM objects.

    Qdrant unavailability is a stage failure — the manager logs it and appends to
    ``result.stages_failed``, causing ARQ to retry. ``_stage_reflect``,
    ``_stage_skills``, and ``_stage_rules`` are all idempotent on retry, so only
    this stage re-runs. Known limitation: a retry produces a near-duplicate Qdrant
    point (same text, different point ID). Full idempotency requires stamping a
    point ID on the execution row — deferred.
    """
    if not rctx.full_reflect:
        return result

    span = current_span()
    domains = ", ".join(rctx.domain_tags.keys()) if rctx.domain_tags else "none"
    desc = (rctx.task_description or "")[:500]
    tool_names = ", ".join(t.get("tool", "?") for t in list(rctx.tool_trace)[:12]) or "none"

    if rctx.status == "completed":
        artifact_summary = (rctx.artifact or "")[:300]
        text = (
            f"Completed {rctx.task_type or 'general'} task: {rctx.task_title}."
            + (f" {desc}" if desc else "")
            + (f" Output: {artifact_summary}" if artifact_summary else "")
            + f" Tools: {tool_names}. Domains: {domains}. Quality: {rctx.heuristic_score:.2f}."
        )
    else:
        error_type = (rctx.error or {}).get("type", "unknown")
        text = (
            f"Failed {rctx.task_type or 'general'} task: {rctx.task_title}."
            + (f" {desc}" if desc else "")
            + f" Tools: {tool_names}. Domains: {domains}."
            + f" Failed ({error_type}). Steps taken: {rctx.step_count}."
        )

    await memory.store_episode(
        str(rctx.agent_id),
        str(rctx.workspace_id),
        {
            "text": text,
            "task_id": str(rctx.task_id),
            "execution_id": str(rctx.execution_id),
            "task_type": rctx.task_type,
            "domain_tags": rctx.domain_tags or {},
            "difficulty": rctx.difficulty,
            "quality_score": rctx.heuristic_score,
            "status": rctx.status,
        },
    )
    await span.emit(
        "reflect.episodic_written",
        {
            "status": rctx.status,
            "step_count": rctx.step_count,
        },
    )
    return result
