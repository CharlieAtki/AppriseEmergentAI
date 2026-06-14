from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tasks import Task

if TYPE_CHECKING:
    from api.schemas.task import CreateTaskRequest


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def create(
        self,
        workspace_id: uuid.UUID,
        organisation_id: uuid.UUID,
        body: CreateTaskRequest,
        idempotency_key: str | None = None,
    ) -> Task:
        task = Task(
            workspace_id=workspace_id,
            organisation_id=organisation_id,
            title=body.title,
            description=body.description,
            status="enriching",
            task_type=body.task_type,
            priority=body.priority,
            deadline_at=body.deadline_at,
            external_ref=body.external_ref,
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

    async def get(self, workspace_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        result = await self._session.execute(
            select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def list(self, workspace_id: uuid.UUID) -> list[Task]:
        result = await self._session.execute(
            select(Task).where(Task.workspace_id == workspace_id).order_by(Task.created_at.desc())
        )
        return list(result.scalars().all())
