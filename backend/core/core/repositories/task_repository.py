from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models.tasks import Task, TaskExecution


class TaskRepository:
    """Concrete TaskRepository backed by SQLAlchemy AsyncSession.

    Construction: pass an AsyncSession obtained from get_session() or span.session().
    The session's transaction boundary is owned by the caller — this class never commits.
    flush() is the only session-level operation exposed beyond staging (add); it exists
    solely for score_and_reserve(), which must flush before enqueue_job().

    API paths: use get(task_id, workspace_id) — workspace ownership enforced in SQL.
    Worker paths: use get_by_id(task_id) — caller already owns the ID by construction.
    Never use get_by_id() in API routers.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
    ) -> Task:
        """Create and stage a new Task, flushing to populate task.id before returning.

        Flushes internally so the caller immediately has a populated id — required
        before enqueuing jobs or building responses. Does not commit; caller owns the
        transaction boundary. Handles idempotency key conflicts by returning the
        existing task if one already exists for this workspace+key.
        """
        task = Task(
            workspace_id=workspace_id,
            organisation_id=organisation_id,
            title=title,
            description=description,
            status=status,
            task_type=task_type,
            priority=priority,
            deadline_at=deadline_at,
            external_ref=external_ref,
            idempotency_key=idempotency_key,
        )
        self._session.add(task)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            if idempotency_key:
                existing = await self._get_by_idempotency_key(workspace_id, idempotency_key)
                if existing:
                    return existing
            raise
        return task

    async def get(self, task_id: uuid.UUID, workspace_id: uuid.UUID) -> Task | None:
        """Fetch a Task by PK with mandatory workspace ownership filter.

        Workspace filter is enforced in SQL — never loads then checks in Python.
        Use this in all API router paths. For internal worker paths, use get_by_id().
        """
        result = await self._session.execute(
            select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, task_id: uuid.UUID) -> Task | None:
        """Fetch a Task by PK with no workspace filter.

        Unscoped by design — for internal worker paths that already own the task ID
        by construction (job arguments, stream events). Never call this from API routers.
        """
        return await self._session.get(Task, task_id)

    async def get_for_execution(self, task_id: uuid.UUID) -> Task | None:
        """Fetch a Task with the relationships needed by execute_task (subtasks).

        Named for the use case, not the ORM operation — callers should not need to
        know which relationships are loaded. If execute_task's needs change, update
        this method, not the callers.
        """
        return await self._session.get(Task, task_id, options=[selectinload(Task.subtasks)])

    async def list_all(
        self,
        workspace_id: uuid.UUID,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[tuple[Task, uuid.UUID | None]]:
        """List tasks newest-first, paired with the agent_id of their latest execution.

        agent_id comes from a correlated subquery over task_executions (a task can
        have zero or more executions; only the most recent one's agent matters for
        a feed row) rather than a JOIN, since a task with no executions yet
        (pending/enriching/open/reserved) must still appear with agent_id=None.
        """
        latest_execution_agent = (
            select(TaskExecution.agent_id)
            .where(TaskExecution.task_id == Task.id)
            .order_by(TaskExecution.started_at.desc().nulls_last())
            .limit(1)
            .correlate(Task)
            .scalar_subquery()
        )
        stmt = select(Task, latest_execution_agent).where(Task.workspace_id == workspace_id)
        if since is not None:
            stmt = stmt.where(Task.created_at >= since)
        stmt = stmt.order_by(Task.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [(task, agent_id) for task, agent_id in result.all()]

    async def get_siblings(self, parent_task_id: uuid.UUID, workspace_id: uuid.UUID) -> list[Task]:
        """Fetch all subtasks sharing the same parent within a workspace."""
        result = await self._session.execute(
            select(Task).where(
                Task.parent_task_id == parent_task_id,
                Task.workspace_id == workspace_id,
            )
        )
        return list(result.scalars().all())

    async def save(self, task: Task) -> None:
        """Stage task for persistence via session.add().

        async for interface consistency with other methods — session.add() is not I/O
        and does not block the event loop. Caller is responsible for flush/commit.
        """
        self._session.add(task)

    async def flush(self) -> None:
        """Delegate to session.flush().

        Exposed for score_and_reserve(), which must flush the task reservation before
        calling enqueue_job(). Do not call speculatively — the session context manager
        commits (and implicitly flushes) on clean exit.
        """
        await self._session.flush()

    async def _get_by_idempotency_key(
        self, workspace_id: uuid.UUID, idempotency_key: str
    ) -> Task | None:
        result = await self._session.execute(
            select(Task).where(
                Task.workspace_id == workspace_id,
                Task.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()
