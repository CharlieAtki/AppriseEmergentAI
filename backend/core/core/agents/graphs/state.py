from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    # add_messages reducer: node functions return only new messages; LangGraph appends them.
    messages: Annotated[list[BaseMessage], add_messages]
    agent_id: str
    task_id: str
    workspace_id: str
    task_type: str
    tool_trace: list[dict]
    artifact: str | None
    step_count: int
