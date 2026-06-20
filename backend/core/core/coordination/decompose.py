from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from core.coordination.task_context import TaskContext
    from core.eventing.activity.task_logger import TaskActivityLogger
    from core.models.agents import Agent
    from core.models.tasks import Task
    from core.repositories.protocols import TaskRepositoryProtocol


class SubtaskSpec(TypedDict, total=False):
    title: str  # required
    description: str
    required_skills: dict[str, float]
    difficulty: float
    task_type: str
    domain_tags: dict[str, Any]


async def decompose_and_publish(
    agent: Agent,
    parent_task: Task,
    subtask_specs: list[SubtaskSpec],
    task_repo: TaskRepositoryProtocol,
    task_ctx: TaskContext,
    task_logger: TaskActivityLogger,
) -> list[Task]:
    """Persist subtasks to Postgres and fire in-process creation events.

    Participates in the caller's transaction via the injected repo — does not
    commit. The caller (worker/jobs/execute_task.py) commits so that subtask
    creation and parent status changes land in one atomic transaction.

    task_repo.flush() is called internally to assign server-generated UUIDs.
    The caller needs task.id to be non-None before publishing to Redis Streams.

    Provenance (parent_task_id, coordinator_agent_id, created_by_agent_id) is
    persisted to Postgres on the Task row. It is intentionally excluded from the
    stream payload — no consumer reads it from the stream, and keeping the payload
    minimal prevents subscriber drift.
    """
    from core.models.tasks import Task as TaskModel  # local import avoids circular

    created: list[TaskModel] = []

    for spec in subtask_specs:
        title = spec.get("title")
        if not title:
            raise ValueError("Each SubtaskSpec must include a 'title'")

        subtask = TaskModel(
            workspace_id=parent_task.workspace_id,
            organisation_id=parent_task.organisation_id,
            parent_task_id=parent_task.id,
            title=title,
            description=spec.get("description"),
            status="open",
            task_type=spec.get("task_type", parent_task.task_type),
            required_skills=spec.get("required_skills", parent_task.required_skills),
            difficulty=spec.get("difficulty", parent_task.difficulty),
            domain_tags=spec.get("domain_tags", parent_task.domain_tags),
            coordinator_agent_id=task_ctx.coordinator_agent_id or agent.id,
            created_by_agent_id=agent.id,
            delegation_depth=task_ctx.delegation_depth + 1,
        )
        await task_repo.save(subtask)
        created.append(subtask)

    await task_repo.flush()

    for subtask in created:
        await task_logger.created(subtask)

    return created
