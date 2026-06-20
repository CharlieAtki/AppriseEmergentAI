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
    agent_id and workspace_id are included in the system message so the LLM always
    knows what to pass those tools.
    """
    agent_id = str(agent.id)
    workspace_id = str(task.workspace_id)

    system_content = "\n".join(
        [
            f"You are agent '{agent.name}' (agent_id: {agent_id}, workspace_id: {workspace_id}).",
            "",
            f"Current skill profile: {json.dumps(agent.skills or {})}",
            f"Influence score: {agent.influence or 0.0:.3f}",
            f"Personality: {json.dumps(agent.personality or {})}",
            "",
            "Available tools — call them when they will improve the outcome:",
            "  search_episodic_memory(agent_id, workspace_id, query)    — past task experiences",
            "  search_procedural_memory(agent_id, workspace_id, domain, query) — generalised rules",
            "  search_social_memory(agent_id, workspace_id, peer_agent_id)    — peer observations",
            "  web_search(query)                                         — external information",
            "  execute_code(code, language)                              — sandboxed code execution",
            "",
            "Always pass your own agent_id and workspace_id shown above when calling memory tools.",
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
        step_count=0,
    )
