from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, StateGraph

from core.agents.graphs.state import GraphState
from core.config import settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph


def build_graph(
    model_with_tools: "BaseChatModel",
    tools: list["BaseTool"],
) -> "CompiledStateGraph":
    """Compile a reusable ReAct graph for one task type.

    Call once at worker startup per task type and store in ctx. Never call inside a job.
    model_with_tools must already have tools bound via model.bind_tools(tools).
    """
    tool_map = {t.name: t for t in tools}

    async def _reason(state: GraphState) -> dict:
        response = await model_with_tools.ainvoke(state["messages"])
        update: dict = {"messages": [response], "step_count": state["step_count"] + 1}
        if not getattr(response, "tool_calls", None):
            update["artifact"] = response.content
        return update

    async def _call_tool(state: GraphState) -> dict:
        last: AIMessage = state["messages"][-1]
        tool_msgs: list[ToolMessage] = []
        traces: list[dict] = []
        for tc in last.tool_calls:
            result = await tool_map[tc["name"]].ainvoke(tc["args"])
            tool_msgs.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
            traces.append({"tool": tc["name"], "args": tc["args"], "result": str(result)})
        return {
            "messages": tool_msgs,
            "tool_trace": [*state["tool_trace"], *traces],
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
