from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
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

    async def get_decompose_execution_id(self, task_id: uuid.UUID) -> uuid.UUID | None:
        """Return the id of the decompose execution record for a task.

        Used by RollupSubtaskHandler to enqueue the reflect job for the coordinator.
        Returns None if the task was not decomposed (self-execute or CFP chain).
        """
        return (
            await self._session.execute(
                select(TaskExecution.id)
                .where(
                    TaskExecution.task_id == task_id,
                    TaskExecution.execution_path == "decompose",
                )
                .limit(1)
            )
        ).scalar()

    async def get_avg_quality_for_completed_tasks(self, task_ids: list[uuid.UUID]) -> float | None:
        """Average quality_score across completed executions for the given task IDs.

        task_ids are Task PKs (not execution IDs) — matches TaskExecution.task_id.
        Used by AgentCreditHandler._subtask_rollup_credits() to compute the quality
        signal for coordinator agents after all subtasks complete.
        Returns None if no completed executions exist.
        """
        return (
            await self._session.execute(
                select(func.avg(TaskExecution.quality_score)).where(
                    TaskExecution.task_id.in_(task_ids),
                    TaskExecution.status == "completed",
                )
            )
        ).scalar()

    async def has_active_for_agent(self, agent_id: uuid.UUID) -> bool:
        """Check if agent has any non-terminal executions.

        Returns True if there are any executing/failed/retry executions; False otherwise.
        Used to guard agent deletion and prevent loss of active execution history.
        """
        result = await self._session.execute(
            select(func.count(TaskExecution.id)).where(
                TaskExecution.agent_id == agent_id,
                TaskExecution.status.in_(["executing", "failed", "retry"]),
            )
        )
        return (result.scalar() or 0) > 0

    async def list_for_agents(
        self,
        workspace_id: uuid.UUID,
        agent_ids: Sequence[uuid.UUID],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[TaskExecution]:
        """Per-agent execution history for the Agent Lanes dashboard panel.

        Uses ix_task_executions_agent_id_started_at (migration 013) — required
        because this runs on every dashboard load.
        """
        if not agent_ids:
            return []
        query = select(TaskExecution).where(
            TaskExecution.workspace_id == workspace_id,
            TaskExecution.agent_id.in_(agent_ids),
        )
        if since is not None:
            query = query.where(TaskExecution.started_at >= since)
        if until is not None:
            query = query.where(TaskExecution.started_at <= until)
        query = query.order_by(TaskExecution.started_at.asc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def save(self, execution: TaskExecution) -> None:
        """Stage execution for persistence. async for interface consistency —
        session.add() is not I/O. On detached objects this is a merge operation,
        re-attaching the execution to the current session.
        """
        self._session.add(execution)
