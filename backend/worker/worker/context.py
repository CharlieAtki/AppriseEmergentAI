from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from core.agents.graphs.factory import build_graph
from core.agents.tools.registry import tool_registry
from core.eventing.bus.in_process_bus import EventBus
from core.eventing.bus.redis_bus import RedisBus
from core.config import settings
from core.database import get_session
from core.intelligence.call_types import CallType
from core.intelligence.llm_router import LLMRouter
from core.intelligence.registry import registry
from core.intelligence.routing_config import resolve_routing
from core.intelligence.sync import sync_models
from core.memory.agent_memory import AgentMemory
from core.vendors.anthropic.provider import AnthropicProvider
from core.vendors.aws.provider import AWSProvider
from core.vendors.azure.provider import AzureProvider
from core.vendors.ollama.provider import OllamaProvider

if TYPE_CHECKING:
    from arq import ArqRedis
    from langgraph.graph.state import CompiledStateGraph


@dataclass(frozen=True)
class WorkerContext:
    graphs: dict[str, "CompiledStateGraph"]  # keyed by task_type
    bus: RedisBus                             # Redis Streams — durable task events
    redis: Redis                              # raw Redis — Pub/Sub (observability) + SETNX (reservations)
    arq_queue: "ArqRedis"                     # ARQ job queue — enqueue_job()
    memory: AgentMemory                       # Qdrant-backed three-tier memory
    llm_router: LLMRouter                     # routes all LLM calls by CallType
    event_bus: EventBus                       # in-process — same-process side effects

    @classmethod
    async def build(cls, arq_queue: "ArqRedis") -> WorkerContext:
        # 1. Self-registration side effects — importing is registering
        import core.vendors.anthropic  # noqa: F401
        import core.vendors.aws  # noqa: F401
        import core.vendors.azure  # noqa: F401
        import core.vendors.ollama  # noqa: F401
        import core.agents.tools.search_episodic  # noqa: F401
        import core.agents.tools.search_procedural  # noqa: F401
        import core.agents.tools.search_social  # noqa: F401
        import core.agents.tools.web_search  # noqa: F401
        import core.agents.tools.execute_code  # noqa: F401

        # 2. Sync in-memory model registry → DB models table
        async with get_session() as session:
            await sync_models(session, registry)

        # 3. Build LLMRouter with all vendor providers
        routing_cfg = resolve_routing(settings.intelligence.routing, workspace_overrides=None)
        # ToDo: Can we make this dynamic rather than hardcoded?
        vendors = {
            "anthropic": AnthropicProvider(settings.anthropic),
            "azure":     AzureProvider(settings.azure),
            "aws":       AWSProvider(settings.aws),
            "ollama":    OllamaProvider(settings.ollama),
        }
        llm_router = LLMRouter(
            vendors=vendors,
            catalog=registry,
            routing=routing_cfg.routing,
            max_concurrent=settings.intelligence.max_concurrent_llm_calls,
            force_heuristic_fallback=settings.intelligence.force_heuristic_fallback,
        )

        # 4. Build AgentMemory — always HTTP client, never embedded mode
        qdrant = AsyncQdrantClient(url=settings.memory.qdrant_url)
        memory = AgentMemory(qdrant)

        # 5. Compile one graph per task type — expensive, done ONCE per process
        model = llm_router.get_chat_model(CallType.EXECUTE)
        graphs: dict[str, CompiledStateGraph] = {
            task_type: build_graph(
                model_with_tools=model.bind_tools(
                    tool_registry.build_for_task_type(task_type, memory=memory)
                ),
                tools=tool_registry.build_for_task_type(task_type, memory=memory),
            )
            for task_type in ["general", "code", "research", "coordination"]
        }

        # 6. Two separate Redis connections — Streams bus vs raw Pub/Sub + locks
        redis = Redis.from_url(settings.redis.url, decode_responses=True)
        bus = await RedisBus.create(settings.redis.url)

        # 7. In-process event bus — must be created from the running event loop
        import asyncio # ToDo: Can we move this import to the top without circular import issues? It's needed for EventBus but also for startup() which imports this module.
        loop = asyncio.get_running_loop()
        event_bus = EventBus(loop=loop)

        return cls(
            graphs=graphs,
            bus=bus,
            redis=redis,
            arq_queue=arq_queue,
            memory=memory,
            llm_router=llm_router,
            event_bus=event_bus,
        )


_context: WorkerContext | None = None


def init_worker_context(wctx: WorkerContext) -> None:
    global _context
    _context = wctx


def get_worker_context() -> WorkerContext:
    if _context is None:
        raise RuntimeError("WorkerContext not initialised — is startup() running?")
    return _context
