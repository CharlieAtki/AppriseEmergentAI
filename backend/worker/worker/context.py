from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from core.agents.graphs.factory import build_universal_graph
from core.agents.tooling.artifact_store import LocalArtifactStore
from core.agents.tooling.registry import tool_registry
from core.config import settings
from core.database import get_session
from core.eventing.activity.centrifugo_publish import make_centrifugo_publish
from core.eventing.bus.in_process_bus import EventBus
from core.eventing.bus.redis_bus import RedisBus
from core.intelligence.llm_router import LLMRouter
from core.intelligence.registry import registry
from core.intelligence.routing_config import resolve_routing
from core.intelligence.sync import sync_models, sync_tools
from core.memory.agent_memory import AgentMemory
from core.memory.collections import ensure_collections
from core.memory.embeddings import get_encoder
from core.memory.resilient_client import ResilientQdrantClient
from core.vendors.anthropic.provider import AnthropicProvider
from core.vendors.aws.provider import AWSProvider
from core.vendors.azure.provider import AzureProvider
from core.vendors.ollama.provider import OllamaProvider
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

if TYPE_CHECKING:
    from arq import ArqRedis
    from core.agents.tooling.artifact_store import ArtifactStore
    from core.eventing.activity.base import PubSubPublishFn
    from core.eventing.bus.protocols import SubscribableBusProtocol
    from langgraph.graph.state import CompiledStateGraph

    from worker.reflection.manager import ReflectionManager


@dataclass(frozen=True)
class WorkerContext:
    graphs: dict[str, CompiledStateGraph]  # single key: "universal"
    bus: SubscribableBusProtocol  # Redis Streams — durable task events
    redis: Redis  # raw Redis — SETNX reservations (Pub/Sub moved to Centrifugo)
    arq_queue: ArqRedis  # ARQ job queue — enqueue_job()
    memory: AgentMemory  # Qdrant-backed three-tier memory
    llm_router: LLMRouter  # routes all LLM calls by CallType
    event_bus: EventBus  # in-process — same-process side effects
    reflection_manager: ReflectionManager  # post-execution learning pipeline
    artifact_store: ArtifactStore  # artifact bytes storage
    centrifugo_http_client: httpx.AsyncClient  # backs centrifugo_publish; closed on shutdown
    centrifugo_publish: (
        PubSubPublishFn  # dashboard/trace event transport — JobSpan.stream, WorkspaceStreamLogger
    )

    @classmethod
    async def build(cls, arq_queue: ArqRedis) -> WorkerContext:
        # 1. Self-registration side effects — importing is registering
        import core.agents.tooling.tool.execute_code
        import core.agents.tooling.tool.file_read
        import core.agents.tooling.tool.file_write
        import core.agents.tooling.tool.search_episodic
        import core.agents.tooling.tool.search_procedural
        import core.agents.tooling.tool.search_social
        import core.agents.tooling.tool.web_search
        import core.vendors.anthropic
        import core.vendors.aws
        import core.vendors.azure
        import core.vendors.ollama  # noqa: F401

        # 2. Sync in-memory registries → DB tables
        async with get_session() as session:
            await sync_models(session, registry)
            await sync_tools(session, tool_registry)

        # 3. Build LLMRouter with all vendor providers
        routing_cfg = resolve_routing(settings.intelligence.routing, workspace_overrides=None)
        vendors = {
            "anthropic": AnthropicProvider(settings.anthropic),
            "azure": AzureProvider(settings.azure),
            "aws": AWSProvider(settings.aws),
            "ollama": OllamaProvider(settings.ollama),
        }
        llm_router = LLMRouter(
            vendors=vendors,
            catalog=registry,
            routing=routing_cfg.routing,
            max_concurrent=settings.intelligence.max_concurrent_llm_calls,
            force_heuristic_fallback=settings.intelligence.force_heuristic_fallback,
        )

        # 4. Build AgentMemory — always HTTP client, never embedded mode
        _raw_qdrant = AsyncQdrantClient(url=settings.memory.qdrant_url)
        await ensure_collections(_raw_qdrant)
        qdrant = ResilientQdrantClient(_raw_qdrant)
        memory = AgentMemory(qdrant)

        # 4b. Pre-warm the fastembed encoder — first-call lazy init races when
        # concurrent jobs hit search_episodic_memory on a cold worker.
        get_encoder()

        # 5. Compile one universal graph — expensive, done ONCE per process.
        # Model and tools are injected per-task via RunnableConfig.configurable in execute_task.
        graphs: dict[str, CompiledStateGraph] = {"universal": build_universal_graph()}

        # 6. Two separate Redis connections — Streams bus vs SETNX reservation locks
        redis = Redis.from_url(settings.redis.url, decode_responses=True)
        bus = await RedisBus.create(settings.redis.url)

        # 6b. Centrifugo publish transport — dashboard/trace events (formerly raw
        # Redis Pub/Sub). One shared httpx client, closed in shutdown().
        centrifugo_http_client = httpx.AsyncClient()
        centrifugo_publish = make_centrifugo_publish(settings.centrifugo, centrifugo_http_client)

        # 7. In-process event bus — must be created from the running event loop
        import asyncio  # local import avoids circular: startup imports this module at module level

        loop = asyncio.get_running_loop()
        event_bus = EventBus(loop=loop)

        from worker.reflection.manager import REFLECT_PIPELINE, ReflectionManager

        reflection_manager = ReflectionManager(
            pipeline=REFLECT_PIPELINE,
            llm_router=llm_router,
            memory=memory,
        )

        artifact_store = LocalArtifactStore()

        return cls(
            graphs=graphs,
            bus=bus,
            redis=redis,
            arq_queue=arq_queue,
            memory=memory,
            llm_router=llm_router,
            event_bus=event_bus,
            reflection_manager=reflection_manager,
            artifact_store=artifact_store,
            centrifugo_http_client=centrifugo_http_client,
            centrifugo_publish=centrifugo_publish,
        )


_context: WorkerContext | None = None


def init_worker_context(wctx: WorkerContext) -> None:
    global _context
    _context = wctx


def get_worker_context() -> WorkerContext:
    if _context is None:
        raise RuntimeError("WorkerContext not initialised — is startup() running?")
    return _context
