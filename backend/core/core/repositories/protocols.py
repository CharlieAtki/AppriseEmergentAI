from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from core.models.agents import Agent
from core.models.observability import ProceduralKnowledgeLog, SkillSnapshot
from core.models.tasks import Task, TaskExecution, WebhookDelivery
from core.models.tenant import Workspace


class TaskRepositoryProtocol(Protocol):
    """Read/write interface for Task persistence. Satisfied by TaskRepository and test fakes.

    Follows the BusProtocol pattern: code types against this protocol, never the concrete class.
    Swap in a FakeTaskRepository in unit tests — no SQLAlchemy mocking required.

    Transaction contract: this protocol never calls commit(). flush() is exposed solely
    for score_and_reserve(), which must flush before enqueue_job(). All other callers
    let the session context manager commit on exit.
    """

    async def create(
        self,
        workspace_id: uuid.UUID,
        organisation_id: uuid.UUID,
        title: str,
        description: str | None,
        status: str,
        task_type: str | None,
        priority: str | None,
        deadline_at: datetime | None,
        external_ref: str | None,
        idempotency_key: str | None,
    ) -> Task: ...

    async def get(self, task_id: uuid.UUID, workspace_id: uuid.UUID) -> Task | None: ...

    # workspace_id is mandatory — enforces tenant ownership at the type level.
    # For internal worker paths that already own the ID by construction, use get_by_id().

    async def get_by_id(self, task_id: uuid.UUID) -> Task | None: ...

    # Unscoped PK lookup. Never call this from API routers — use get() instead.

    async def get_for_execution(self, task_id: uuid.UUID) -> Task | None: ...

    # Loads Task with the relationships needed by execute_task (subtasks).
    # Named for the use case, not the ORM operation — loading strategy is an impl detail.

    async def list(self, workspace_id: uuid.UUID) -> list[Task]: ...

    async def get_siblings(
        self, parent_task_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[Task]: ...

    async def save(self, task: Task) -> None: ...

    # Stages task for persistence. async for interface consistency — session.add() is not I/O.

    async def flush(self) -> None: ...

    # Exposes session.flush() for score_and_reserve(), which must flush before enqueue_job().
    # Do not call flush() speculatively — callers own the transaction boundary.


class AgentRepositoryProtocol(Protocol):
    """Read/write interface for Agent persistence. Satisfied by AgentRepository and test fakes.

    Same transaction contract as TaskRepositoryProtocol — never commits, never flushes
    internally (except create(), which flushes to populate the auto-generated id).
    """

    async def create(
        self,
        workspace_id: uuid.UUID,
        organisation_id: uuid.UUID,
        name: str,
        skills: dict[str, Any] | None,
        personality: dict[str, Any] | None,
    ) -> Agent: ...

    async def get(self, agent_id: uuid.UUID, workspace_id: uuid.UUID) -> Agent | None: ...

    async def get_by_id(self, agent_id: uuid.UUID) -> Agent | None: ...

    # Unscoped PK lookup. Never call this from API routers — use get() instead.

    async def get_for_execution(self, agent_id: uuid.UUID) -> Agent | None: ...

    # Loads Agent with task_executions. Named for the use case; loading strategy is impl detail.

    async def get_for_update(self, agent_id: uuid.UUID) -> Agent | None: ...

    # Acquires a row-level lock (with_for_update=True). Used by _stage_skills to prevent
    # concurrent skill overwrites between the reflect pipeline and execute_task skill decay.

    async def get_active_for_bidding(
        self,
        workspace_id: uuid.UUID,
        exclude_id: uuid.UUID | None = None,
    ) -> list[Agent]: ...

    # Active agents with task_executions loaded for bid scoring.
    # exclude_id omits the initiating agent on the CFP path.

    async def get_all_active(
        self,
        workspace_id: uuid.UUID,
        exclude_id: uuid.UUID | None = None,
    ) -> list[Agent]: ...

    # Active agents, no eager load. exclude_id for social_memory (excludes the completer).

    async def list(self, workspace_id: uuid.UUID) -> list[Agent]: ...

    async def update_fields(
        self,
        agent: Agent,
        *,
        name: str | None = None,
        status: str | None = None,
    ) -> Agent: ...

    # Mutates fields in-place and stages the agent. Caller is responsible for flush/commit.

    async def save(self, agent: Agent) -> None: ...


class TaskExecutionRepositoryProtocol(Protocol):
    """Read/write interface for TaskExecution persistence.

    TaskExecution is an aggregate root — its lifecycle is driven by job execution,
    not by Task CRUD. It is created once (always at status="executing"), then
    carried as a detached ORM object across multiple session blocks during the job.
    session.add() calls in later phases are merges, re-attaching the detached object.

    Same transaction contract as the other protocols: never commits, never flushes
    internally (except create(), which flushes to populate the auto-generated id).
    """

    async def create(
        self,
        workspace_id: uuid.UUID,
        organisation_id: uuid.UUID,
        task_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> TaskExecution: ...

    # Always creates with status="executing" — no valid path to create at any other
    # status. Flushes to populate execution.id before returning.

    async def get_by_id(self, execution_id: uuid.UUID) -> TaskExecution | None: ...

    # Unscoped PK lookup — for internal worker paths only.

    async def get_for_reflection(self, execution_id: uuid.UUID) -> TaskExecution | None: ...

    # Loads execution with selectinload(task, agent) in one round-trip.
    # Callers access execution.task and execution.agent as already-loaded attributes.

    async def get_delegation_contributors(
        self, task_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[TaskExecution]: ...

    # Executions with execution_path in ("cfp", "decompose") for a given task.
    # Used by compute_delegation_credits to identify coordinating agents.

    async def get_decompose_execution_id(self, task_id: uuid.UUID) -> uuid.UUID | None: ...

    # Return the id of the decompose execution record for a task.
    # Returns None if the task was not decomposed (self-execute or CFP chain).

    async def get_avg_quality_for_completed_tasks(
        self, task_ids: list[uuid.UUID]
    ) -> float | None: ...

    # Average quality_score across completed executions for the given Task PKs.
    # Returns None if no completed executions exist.

    async def save(self, execution: TaskExecution) -> None: ...

    # Stages execution for persistence. On detached objects this is a merge —
    # re-attaches the execution to the current session. async for interface consistency.


class SkillRepositoryProtocol(Protocol):
    """Read/write interface for SkillSnapshot audit records.

    SkillSnapshot is a write-once audit record per task execution. get_by_execution()
    is the application-level idempotency guard; the DB unique partial index on
    execution_id is the backstop. record() never flushes or commits.
    """

    async def get_by_execution(
        self, execution_id: uuid.UUID, agent_id: uuid.UUID
    ) -> SkillSnapshot | None: ...

    # Idempotency check — returns existing snapshot for this execution if present.

    async def record(
        self,
        agent_id: uuid.UUID,
        organisation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        skills: dict[str, float],
        execution_id: uuid.UUID,
    ) -> None: ...

    # Stage a SkillSnapshot for the audit trail. Does not flush or commit.


class InfluenceRepositoryProtocol(Protocol):
    """Write-only interface for InfluenceSnapshot audit records.

    Multiple snapshots per task completion are expected (executor + coordinators).
    No idempotency guard — each record() call adds a new audit row.
    """

    async def record(
        self,
        agent_id: uuid.UUID,
        organisation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        influence: float,
    ) -> None: ...

    # Stage an InfluenceSnapshot for the audit trail. Does not flush or commit.


class ProceduralKnowledgeRepositoryProtocol(Protocol):
    """Read/write interface for ProceduralKnowledgeLog — three-phase dual-write support.

    Phase 1: record() inserts the audit row and returns its UUID.
    Phase 2: Qdrant write (caller-owned).
    Phase 3: get_by_id() + save() stamps vector_store_ref after Qdrant succeeds.

    record() generates the UUID internally and returns it so the caller can bridge
    Phase 1 and Phase 3 across separate session blocks.
    """

    async def get_by_execution(self, execution_id: uuid.UUID) -> ProceduralKnowledgeLog | None: ...

    # Idempotency check — returns existing log for this execution if present.

    async def get_by_id(self, log_id: uuid.UUID) -> ProceduralKnowledgeLog | None: ...

    # PK lookup — used by Phase 3 to stamp vector_store_ref after Qdrant succeeds.

    async def record(
        self,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        domain: str,
        rule_text: str,
        execution_id: uuid.UUID,
    ) -> uuid.UUID: ...

    # Stage Phase 1 insert. Returns the generated log_id for use in Phase 3.

    async def save(self, log: ProceduralKnowledgeLog) -> None: ...

    # Stage Phase 3 stamp — marks both Postgres and Qdrant writes as complete.


class WorkspaceRepositoryProtocol(Protocol):
    """Single-workspace PK lookup. Never use for cross-workspace admin queries.

    Cross-workspace queries belong on WorkspaceAdminRepository (deferred until
    the cron job layer is refactored). Importing WorkspaceAdminRepository is a
    privilege signal — any file that does so touches all workspaces.
    """

    async def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None: ...

    # Unscoped PK lookup — for internal worker paths only (e.g. deliver_webhook).
    # Never call this from API routers — use a workspace-scoped query instead.


class WebhookDeliveryRepositoryProtocol(Protocol):
    """Read/write interface for WebhookDelivery.

    Idempotency: get_by_delivery_id() checks for existing terminal records before
    create() is called. Both run in the same session block so there is no TOCTOU gap.

    create() generates delivery_id internally — caller captures delivery.delivery_id
    as a local string inside the session block before the context manager exits.

    No save() — session 2 mutations on the loaded record are auto-tracked by SQLAlchemy.
    """

    async def get_by_delivery_id(self, delivery_id: str) -> WebhookDelivery | None: ...

    # Fetch by stable external dedupe key — for idempotency check and outcome recording.

    async def create(
        self,
        organisation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        task_execution_id: uuid.UUID,
        target_url: str,
    ) -> WebhookDelivery: ...
