from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ReflectContext:
    """Immutable snapshot of all state the reflection pipeline needs.

    Built in ``worker/jobs/reflect.py`` from ORM objects while a session is open,
    then passed unchanged through every pipeline stage. Frozen so stages cannot
    accidentally corrupt shared context; tuple/dict fields are read-only by
    convention — stages must not mutate them.

    Fields:
        task_id / agent_id / execution_id / workspace_id / organisation_id:
            Primary keys extracted before the session closes. Stages open their
            own sessions using these rather than holding a live ORM reference.
        task_title / task_description / task_type / required_skills / difficulty / domain_tags:
            Task metadata used by prompt builders and stage gate conditions.
        status:
            Execution outcome. Every stage branches on this — prompts, episodic
            text, and rule extraction all differ between "completed" and "failed".
        artifact / error / tool_trace:
            Raw execution outputs. ``artifact`` is the agent's final answer;
            ``error`` is the structured failure dict; ``tool_trace`` is the
            sequence of tool calls made during execution.
        heuristic_score:
            Authoritative quality signal for the pipeline. Computed by
            ``score_outcome()`` at execution time and written to
            ``TaskExecution.quality_score``. Used by ``_stage_skills`` for delta
            magnitude and passed as context to the REFLECT prompt.
        full_reflect:
            True when difficulty >= 3.0 or step_count > 3. Gates the "rules" stage
            — procedural rule extraction and supersession only run on non-trivial
            executions.
        step_count:
            Number of tool calls during execution (len of tool_trace at load time).
        agent_skills:
            Read-only snapshot of the agent's skill profile at reflection time.
            Stages that write skills load the Agent fresh from DB for atomic writes.
    """

    task_id:          uuid.UUID
    agent_id:         uuid.UUID
    execution_id:     uuid.UUID
    workspace_id:     uuid.UUID
    organisation_id:  uuid.UUID
    task_title:       str
    task_description: str | None
    task_type:        str | None
    required_skills:  dict[str, float]
    difficulty:       float | None
    domain_tags:      dict | None
    status:           Literal["completed", "failed"]
    artifact:         str | None
    error:            dict | None
    tool_trace:       tuple          # immutable — stages must not mutate shared context
    heuristic_score:  float          # authoritative quality signal — score_outcome() result
    full_reflect:     bool           # difficulty >= 3.0 or step_count > 3
    step_count:       int
    agent_skills:     dict[str, float]


@dataclass
class PipelineResult:
    """Mutable accumulator passed through each pipeline stage.

    ``ReflectionManager.run()`` creates one empty instance before the pipeline
    starts and hands it to every stage in sequence. Each stage reads previous
    outputs and writes its own. ``stages_run`` and ``stages_failed`` are appended
    by the manager, not by stage functions.

    Fields:
        skill_domains:          Skill names the LLM identified as exercised.
                                Set by ``_stage_reflect``; consumed by
                                ``_stage_skills`` to compute targeted deltas.
        new_skill_suggestions:  New skills suggested by the LLM to seed at 0.1
                                if absent from the agent's current profile.
        rule:                   Generalised procedural rule text extracted on the
                                full_reflect path. None if no specific rule was
                                produced or the execution was lightweight.
        verdict:                Supersession verdict relative to existing Qdrant
                                rules — "supersedes", "complements", or
                                "contradicts". None when no existing rule matched.
        superseded_ids:         Qdrant point IDs of rules this new rule supersedes.
        stages_run:             Names of stages that completed successfully, in order.
        stages_failed:          Names of stages that raised an exception.
    """

    skill_domains:         list[str]        = field(default_factory=list)
    new_skill_suggestions: list[str]        = field(default_factory=list)
    rule:                  str | None       = None
    verdict:               str | None       = None
    superseded_ids:        list[str] | None = None
    stages_run:            list[str]        = field(default_factory=list)
    stages_failed:         list[str]        = field(default_factory=list)