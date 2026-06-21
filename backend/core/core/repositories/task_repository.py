from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models.tasks import Task


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

    async def list_all(self, workspace_id: uuid.UUID) -> list[Task]:
        result = await self._session.execute(
            select(Task).where(Task.workspace_id == workspace_id).order_by(Task.created_at.desc())
        )
        return list(result.scalars().all())

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
