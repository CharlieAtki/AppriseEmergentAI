"""Graph state types for LangGraph execution.

**Why TypedDict, not a frozen dataclass?**

LangGraph mandates subscriptable dict state — frozen dataclasses don't support
``state["key"]`` access. The ``add_messages`` reducer also requires a TypedDict or
Pydantic annotation, not a dataclass field.

This is NOT a domain entity crossing a service boundary — it is runtime computation
state owned entirely by the graph. The DDD pattern here is the *node function
signature*, not a ``from_domain()`` mapping. Consequence: all TypedDict fields must be
accessed via direct subscription (``state["key"]``), never ``state.get("key")``.
That preserves the typed contract and lets the type-checker catch mistyped keys.

``ToolTrace`` is also a TypedDict (not frozen dataclass) so it serialises to JSONB
without conversion when written to ``TaskExecution.tool_trace``.

Compare with:
  ``GraphConfig``  — frozen dataclass; parses ``RunnableConfig.configurable`` at node boundary
  ``ArqJobMeta``   — frozen dataclass; parses ARQ's raw ``ctx`` dict at job boundary
  ``GraphState``   — TypedDict; LangGraph mandates the type, not a design choice
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ToolTrace(TypedDict):
    """Typed record for a single tool invocation within a graph run.

    Remains a TypedDict (not a frozen dataclass) so it serialises to JSONB
    without conversion — TaskExecution.tool_trace stores these directly.
    """

    tool: str
    args: dict[str, Any]
    result: str


class GraphState(TypedDict):
    # add_messages reducer: node functions return only new messages; LangGraph appends them.
    messages: Annotated[list[BaseMessage], add_messages]
    agent_id: str
    task_id: str
    workspace_id: str
    task_type: str
    tool_trace: list[ToolTrace]
    artifact: str | None  # LLM's final text output
    artifact_id: (
        str | None
    )  # UUID ref to artifacts table; set by any tool returning {"artifact_id": ...}
    step_count: int
    skill_tags_used: list[str]  # accumulated per tool call; feeds RL update in reflect job
