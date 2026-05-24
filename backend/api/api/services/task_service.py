from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.tasks import Task

if TYPE_CHECKING:
    from api.schemas.task import CreateTaskRequest


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        workspace_id: uuid.UUID,
        organisation_id: uuid.UUID,
        body: CreateTaskRequest,
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
            idempotency_key=body.idempotency_key,
        )
        self._session.add(task)
        await self._session.flush()
        return task

    async def get(self, workspace_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        result = await self._session.execute(
            select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def list(self, workspace_id: uuid.UUID) -> list[Task]:
        result = await self._session.execute(
            select(Task)
            .where(Task.workspace_id == workspace_id)
            .order_by(Task.created_at.desc())
        )
        return list(result.scalars().all())
