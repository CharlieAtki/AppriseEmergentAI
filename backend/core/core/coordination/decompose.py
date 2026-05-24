from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from core.eventing.activity.task_logger import TaskActivityLogger
    from core.eventing.activity.task_stream_logger import TaskStreamLogger
    from core.coordination.task_context import TaskContext
    from core.models.agents import Agent
    from core.models.tasks import Task


class SubtaskSpec(TypedDict, total=False):
    title: str  # required
    description: str
    required_skills: dict[str, float]
    difficulty: float
    task_type: str
    domain_tags: dict


async def decompose_and_publish(
    agent: Agent,
    parent_task: Task,
    subtask_specs: list[SubtaskSpec],
    session: AsyncSession,
    stream_logger: TaskStreamLogger,
    task_ctx: TaskContext,
    task_logger: TaskActivityLogger,
) -> list[Task]:
    """Persist subtasks to Postgres and publish each onto the task stream.

    The caller (worker/jobs/execute_task.py) is responsible for generating
    subtask_specs — either via llm_router.decompose() or a heuristic. This
    function only handles persistence and event publishing so that it stays
    LLM-free and testable in isolation.

    Ordering invariant: in-process TaskActivityLogger events fire before cross-process
    stream events. Same-process handlers (e.g. RollupSubtaskHandler) must see the
    subtask creation before Redis subscribers attempt to bid on it.

    The session is NOT committed here; the caller commits so all writes land in one
    transaction alongside any other state changes (e.g. updating the parent task status
    to "executing"). session.flush() is called internally to assign UUIDs — the stream
    logger needs task.id to be non-None before publishing.

    Provenance (parent_task_id, coordinator_agent_id, created_by_agent_id) is persisted
    to Postgres on the Task row. It is intentionally excluded from the stream payload —
    no consumer reads it from the stream, and keeping the payload minimal prevents
    subscriber drift.
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
            status="pending",
            task_type=spec.get("task_type", parent_task.task_type),
            required_skills=spec.get("required_skills", parent_task.required_skills),
            difficulty=spec.get("difficulty", parent_task.difficulty),
            domain_tags=spec.get("domain_tags", parent_task.domain_tags),
            coordinator_agent_id=task_ctx.coordinator_agent_id or agent.id,
            created_by_agent_id=agent.id,
            delegation_depth=task_ctx.delegation_depth + 1,
        )
        session.add(subtask)
        created.append(subtask)

    # Flush to assign server-generated UUIDs without committing.
    await session.flush()

    # Fire in-process events first so same-process handlers see the creation
    # before cross-process subscribers are notified via Redis.
    for subtask in created:
        await task_logger.created(subtask)

    for subtask in created:
        await stream_logger.task_created(subtask)

    return created
