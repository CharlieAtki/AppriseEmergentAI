from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.intelligence.enrichment import EnrichmentOverrides
from core.repositories.task_repository import TaskRepository

if TYPE_CHECKING:
    from core.models.tasks import Task


@dataclass(frozen=True)
class CreateTaskCommand:
    """Immutable write intent — router constructs this from HTTP input; service never imports HTTP schemas."""

    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    title: str
    description: str | None
    task_type: str | None
    priority: str | None
    deadline_at: datetime | None
    external_ref: str | None
    idempotency_key: str | None
    overrides: EnrichmentOverrides | None


@dataclass(frozen=True)
class TaskData:
    """ORM boundary DTO — the Task ORM model never leaves the service layer; callers hold this instead."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    organisation_id: uuid.UUID
    status: str
    title: str
    description: str | None
    task_type: str | None
    priority: str | None
    deadline_at: datetime | None
    external_ref: str | None
    idempotency_key: str | None
    required_skills: Mapping[str, float] | None
    difficulty: float | None
    domain_tags: Mapping[str, Any] | None
    created_at: datetime | None
    # Latest execution's agent, when one exists — None for tasks with no execution
    # yet (pending/enriching/open/reserved). Only list() currently joins this; get()
    # leaves it None (see TaskService.get's docstring).
    agent_id: uuid.UUID | None = None

    @classmethod
    def from_domain(cls, task: Task, agent_id: uuid.UUID | None = None) -> TaskData:
        # Explicit field mapping — mirrors TaskContext.from_task(); no hidden ORM introspection.
        return cls(
            id=task.id,
            workspace_id=task.workspace_id,
            organisation_id=task.organisation_id,
            status=task.status,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            priority=task.priority,
            deadline_at=task.deadline_at,
            external_ref=task.external_ref,
            idempotency_key=task.idempotency_key,
            required_skills=dict(task.required_skills)
            if task.required_skills is not None
            else None,
            difficulty=task.difficulty,
            domain_tags=dict(task.domain_tags) if task.domain_tags is not None else None,
            created_at=task.created_at,
            agent_id=agent_id,
        )


class TaskService:
    """Task lifecycle boundary — accepts Commands, returns TaskData; ORM never escapes."""

    def __init__(self, repo: TaskRepository) -> None:
        self._repo = repo

    async def create(self, cmd: CreateTaskCommand) -> TaskData:
        # Status starts as "enriching" — the enrich_task worker job transitions it forward.
        task = await self._repo.create(
            workspace_id=cmd.workspace_id,
            organisation_id=cmd.organisation_id,
            title=cmd.title,
            description=cmd.description,
            status="enriching",
            task_type=cmd.task_type,
            priority=cmd.priority,
            deadline_at=cmd.deadline_at,
            external_ref=cmd.external_ref,
            idempotency_key=cmd.idempotency_key,
        )
        return TaskData.from_domain(task)

    async def get(self, task_id: uuid.UUID, workspace_id: uuid.UUID) -> TaskData | None:
        """Fetch one task's detail.

        agent_id is always None here — unlike list(), this path doesn't join the
        latest TaskExecution. Known gap for a future pass: extend this endpoint with
        execution/bid history, tool trace, and failure reasoning once a detail view
        needs to fetch that on demand (rather than joining it here up front).
        """
        task = await self._repo.get(task_id, workspace_id)
        return TaskData.from_domain(task) if task is not None else None

    async def list(
        self,
        workspace_id: uuid.UUID,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[TaskData]:
        rows = await self._repo.list_all(workspace_id, since=since, limit=limit)
        return [TaskData.from_domain(t, agent_id=agent_id) for t, agent_id in rows]
