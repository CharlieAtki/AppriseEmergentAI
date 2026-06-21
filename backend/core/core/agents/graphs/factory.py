"""LangGraph graph construction and node functions.

**Separation of concerns**

``build_universal_graph()`` owns graph topology — compiled once at worker startup,
reused across all tasks. Model and tools are never baked in at compile time.

``_reason`` / ``_call_tool`` / ``_route`` are module-level pure async functions. They
take ``GraphState`` and ``RunnableConfig`` — domain objects only, no infrastructure.
No class hierarchy is needed; LangGraph wires them by reference.

**Typed boundaries**

``GraphConfig`` is the parse-at-boundary value object for ``RunnableConfig.configurable``
(same rule as ``ArqJobMeta.from_ctx()`` and service Commands). Raw
``config["configurable"]`` keys never appear downstream of ``GraphConfig.from_runnable()``.

``GraphState`` is a TypedDict — LangGraph mandates it (see ``state.py`` for the full
rationale). All node functions access state fields via direct subscription
(``state["key"]``), never ``state.get("key")``. TypedDict fields are always present
because ``build_initial_state()`` initialises every field; using ``.get()`` would imply
the key might be absent, which breaks the typed contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from core.agents.graphs.state import GraphState, ToolTrace
from core.config import settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph


@dataclass(frozen=True)
class GraphConfig:
    """Typed value object for per-task graph configuration.

    Parsed from RunnableConfig.configurable at the node boundary — never
    accessed as raw dict keys downstream. Follows CLAUDE.md "parse at boundary" rule.
    """

    model: BaseChatModel
    tool_map: dict[str, BaseTool]
    skill_tag_map: dict[str, frozenset[str]] = field(default_factory=dict)

    @classmethod
    def from_runnable(cls, config: RunnableConfig) -> GraphConfig:
        cfg = config["configurable"]
        return cls(
            model=cfg["model"],
            tool_map=cfg["tool_map"],
            skill_tag_map=cfg.get("skill_tag_map", {}),
        )


async def _reason(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    cfg = GraphConfig.from_runnable(config)
    response = await cfg.model.ainvoke(state["messages"])
    update: dict[str, Any] = {"messages": [response], "step_count": state["step_count"] + 1}
    if not getattr(response, "tool_calls", None):
        update["artifact"] = response.content
    return update


async def _call_tool(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    cfg = GraphConfig.from_runnable(config)
    last: AIMessage = state["messages"][-1]

    tool_msgs: list[ToolMessage] = []
    traces: list[ToolTrace] = []
    new_skill_tags: list[str] = list(state["skill_tags_used"])
    artifact_id: str | None = state["artifact_id"]

    for tc in last.tool_calls:
        tool_name: str = tc["name"]
        try:
            result = await cfg.tool_map[tool_name].ainvoke(tc["args"])
            result_str = str(result)
        except Exception as exc:
            result_str = f"[tool error] {type(exc).__name__}: {exc}"

        tool_msgs.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))
        traces.append(ToolTrace(tool=tool_name, args=tc["args"], result=result_str))

        # Accumulate RL skill tags for each successful tool call
        tags = cfg.skill_tag_map.get(tool_name, frozenset())
        new_skill_tags.extend(t for t in tags if t not in new_skill_tags)

        # Protocol-based artifact detection: any tool returning {"artifact_id": ...}
        # signals it wrote a stored artifact. No coupling to a specific tool name.
        if not result_str.startswith("[tool error]"):
            try:
                data = json.loads(result_str)
                if isinstance(data, dict) and "artifact_id" in data:
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


def build_universal_graph() -> CompiledStateGraph:
    """Compile a single universal ReAct graph.

    Call once at worker startup and store in WorkerContext. Never call inside a job.
    Model, tool_map, and skill_tag_map are injected per-task via RunnableConfig.configurable,
    parsed into GraphConfig at each node boundary.
    """
    g = StateGraph(GraphState)
    g.add_node("reason", _reason)
    g.add_node("call_tool", _call_tool)
    g.set_entry_point("reason")
    g.add_conditional_edges("reason", _route)
    g.add_edge("call_tool", "reason")
    return g.compile()
