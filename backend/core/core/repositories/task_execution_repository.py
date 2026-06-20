from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models.tasks import TaskExecution


class TaskExecutionRepository:
    """Concrete TaskExecutionRepository backed by SQLAlchemy AsyncSession.

    TaskExecution is an aggregate root — its lifecycle is driven by job execution,
    not Task CRUD. Executions are created once at status="executing", then carried
    as detached ORM objects across multiple session blocks. The save() calls in later
    phases are SQLAlchemy merges, re-attaching the detached execution to a new session.

    Transaction contract: never calls commit(). Callers own the transaction boundary
    via span.session() or get_session() context managers. create() flushes to populate
    the auto-generated id — the caller needs it before the session closes.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        workspace_id: uuid.UUID,
        organisation_id: uuid.UUID,
        task_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> TaskExecution:
        # status is always "executing" at creation — the state machine has no valid
        # path to create an execution at any other status. started_at is stamped here
        # because the repo owns the creation contract, not the caller.
        execution = TaskExecution(
            task_id=task_id,
            agent_id=agent_id,
            organisation_id=organisation_id,
            workspace_id=workspace_id,
            status="executing",
            started_at=datetime.now(UTC),
        )
        self._session.add(execution)
        await self._session.flush()  # populate auto-generated id before caller uses it
        return execution

    async def get_by_id(self, execution_id: uuid.UUID) -> TaskExecution | None:
        """Unscoped PK lookup — for internal worker paths only."""
        return await self._session.get(TaskExecution, execution_id)

    async def get_for_reflection(self, execution_id: uuid.UUID) -> TaskExecution | None:
        """Load execution with task and agent in one round-trip via ORM graph traversal.

        Eliminates the 3-query pattern previously needed in reflect.py. Callers access
        execution.task and execution.agent as already-loaded attributes — no further
        DB calls needed for the reflect pipeline load phase.

        selectinload matches the established pattern in this codebase and avoids
        Cartesian product risk if relationships ever grow to collections.
        """
        return await self._session.get(
            TaskExecution,
            execution_id,
            options=[selectinload(TaskExecution.task), selectinload(TaskExecution.agent)],
        )

    async def get_delegation_contributors(
        self, task_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[TaskExecution]:
        """Executions that routed this task (execution_path in cfp, decompose).

        Used by compute_delegation_credits to identify which agents coordinated
        and what credit signal they receive.
        """
        result = await self._session.execute(
            select(TaskExecution).where(
                TaskExecution.task_id == task_id,
                TaskExecution.workspace_id == workspace_id,
                TaskExecution.execution_path.in_(["cfp", "decompose"]),
                TaskExecution.status == "completed",
            )
        )
        return list(result.scalars().all())

    async def save(self, execution: TaskExecution) -> None:
        """Stage execution for persistence. async for interface consistency —
        session.add() is not I/O. On detached objects this is a merge operation,
        re-attaching the execution to the current session.
        """
        self._session.add(execution)
