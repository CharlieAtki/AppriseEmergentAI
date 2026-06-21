from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from core.agents.graphs.state import GraphState
from core.config import settings

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


def build_universal_graph() -> CompiledStateGraph:
    """Compile a single universal ReAct graph.

    Call once at worker startup and store in WorkerContext. Never call inside a job.
    Model, tool_map, and skill_tag_map are injected per-task via RunnableConfig.configurable.
    """

    async def _reason(state: GraphState, config: RunnableConfig) -> dict:
        model = config["configurable"]["model"]
        response = await model.ainvoke(state["messages"])
        update: dict = {"messages": [response], "step_count": state["step_count"] + 1}
        if not getattr(response, "tool_calls", None):
            update["artifact"] = response.content
        return update

    async def _call_tool(state: GraphState, config: RunnableConfig) -> dict:
        tool_map: dict = config["configurable"]["tool_map"]
        skill_tag_map: dict[str, frozenset[str]] = config["configurable"].get("skill_tag_map", {})

        last: AIMessage = state["messages"][-1]
        tool_msgs: list[ToolMessage] = []
        traces: list[dict] = []
        new_skill_tags: list[str] = list(state.get("skill_tags_used") or [])
        artifact_id: str | None = state.get("artifact_id")

        for tc in last.tool_calls:
            tool_name = tc["name"]
            try:
                result = await tool_map[tool_name].ainvoke(tc["args"])
                result_str = str(result)
            except Exception as exc:
                result_str = f"[tool error] {type(exc).__name__}: {exc}"

            tool_msgs.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))
            traces.append({"tool": tool_name, "args": tc["args"], "result": result_str})

            # Accumulate RL skill tags for successful tool calls
            tags = skill_tag_map.get(tool_name, frozenset())
            new_skill_tags.extend(t for t in tags if t not in new_skill_tags)

            # Detect file_write artifact — extract artifact_id into state
            if tool_name == "file_write" and not result_str.startswith("[tool error]"):
                try:
                    data = json.loads(result_str)
                    if "artifact_id" in data:
                        artifact_id = data["artifact_id"]
                except json.JSONDecodeError, TypeError:
                    pass

        return {
            "messages": tool_msgs,
            "tool_trace": [*state["tool_trace"], *traces],
            "skill_tags_used": new_skill_tags,
            "artifact_id": artifact_id,
        }

    def _route(state: GraphState) -> str:
        if state["step_count"] >= settings.intelligence.max_graph_steps:
            return END
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "call_tool"
        return END

    g = StateGraph(GraphState)
    g.add_node("reason", _reason)
    g.add_node("call_tool", _call_tool)
    g.set_entry_point("reason")
    g.add_conditional_edges("reason", _route)
    g.add_edge("call_tool", "reason")
    return g.compile()
