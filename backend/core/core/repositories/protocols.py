from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from core.models.agents import Agent
from core.models.tasks import Task, TaskExecution


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

    async def save(self, execution: TaskExecution) -> None: ...

    # Stages execution for persistence. On detached objects this is a merge —
    # re-attaches the execution to the current session. async for interface consistency.
