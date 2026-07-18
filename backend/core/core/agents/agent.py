from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from core.agents.graphs.state import GraphState

if TYPE_CHECKING:
    from core.models.agents import Agent
    from core.models.tasks import Task


def build_initial_state(agent: Agent, task: Task) -> GraphState:
    """Assemble the initial GraphState for a graph invocation.

    Pure function — no I/O, no async, no DB reads. The worker loads Agent and Task
    rows from Postgres before calling this.

    Memory retrieval is NOT done upfront. The agent calls search_episodic_memory,
    search_procedural_memory, and search_social_memory as tool calls mid-execution.
    agent_id and workspace_id are baked into tool closures — the LLM does not pass them.
    """
    agent_id = str(agent.id)
    workspace_id = str(task.workspace_id)

    system_content = "\n".join(
        [
            f"You are agent '{agent.name}'.",
            "",
            f"Current skill profile: {json.dumps(agent.skills or {})}",
            f"Influence score: {agent.influence or 0.0:.3f}",
            "",
            "Use available tools when they will improve the outcome.",
            "When you have finished, your final message should contain the complete output for the task.",
            "Do not call further tools after producing the final output.",
        ]
    )

    task_content = "\n".join(
        filter(
            None,
            [
                f"Task: {task.title}",
                f"Description: {task.description or '(no description provided)'}",
                f"Type: {task.task_type or 'general'}",
                f"Required skills: {json.dumps(task.required_skills or {})}",
                f"Difficulty: {task.difficulty or 1.0:.1f} / 5.0",
                f"Deadline: {task.deadline_at.isoformat()}" if task.deadline_at else None,
            ],
        )
    )

    return GraphState(
        messages=[
            SystemMessage(content=system_content),
            HumanMessage(content=task_content),
        ],
        agent_id=agent_id,
        task_id=str(task.id),
        workspace_id=workspace_id,
        task_type=task.task_type or "general",
        tool_trace=[],
        artifact=None,
        artifact_id=None,
        step_count=0,
        skill_tags_used=[],
    )
