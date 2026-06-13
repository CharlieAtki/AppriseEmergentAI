from __future__ import annotations

import asyncio

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.intelligence.call_types import CallType
from core.intelligence.registry import ModelRegistry
from core.utils.retry import is_retryable_http, retry_async
from core.vendors.base import VendorProvider

_FALLBACK_STUBS: dict[CallType, str] = {
    CallType.EVALUATE:      '{"decision":"self_execute","reasoning":"heuristic fallback"}',
    CallType.REFLECT:       '{"skill_domains":[],"new_skill_suggestions":[],"generalised_rule":null,"verdict":null,"superseded_ids":[]}',
    CallType.DECOMPOSE:     '{"subtasks":[]}',
    CallType.ENRICH:        '{"required_skills":{},"difficulty":1.0,"task_type":"general","domain_tags":{}}',
    CallType.CURATE_MEMORY: '{"flagged":[]}',
}

_JSON_INSTRUCTION = (
    "\n\nRespond ONLY with valid JSON matching the schema above. "
    "No markdown fences, no explanatory text."
)


def _to_langchain_messages(messages: list[dict]) -> list:
    role_map: dict[str, type] = {"system": SystemMessage, "user": HumanMessage}
    return [role_map[m["role"]](content=m["content"]) for m in messages]


class LLMRouter:
    """Routes LLM calls by call type to the registered model.

    Workers construct one LLMRouter at startup (via the ARQ startup hook) and
    reuse it for every job. The semaphore caps concurrent inference across all
    jobs running in the same worker process.
    """

    def __init__(
        self,
        vendors: dict[str, VendorProvider],
        catalog: ModelRegistry,
        routing: dict[str, str],
        *,
        max_concurrent: int = 5,
        force_heuristic_fallback: bool = False,
    ) -> None:
        self._vendors = vendors
        self._catalog = catalog
        self._routing = {CallType(k): v for k, v in routing.items()}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._fallback = force_heuristic_fallback
        self._model_cache: dict[str, BaseChatModel] = {}

    async def complete(
        self,
        messages: list[dict],
        call_type: CallType,
        *,
        json_mode: bool = False,
        routing_override: dict[str, str] | None = None,
    ) -> str:
        if self._fallback:
            return _FALLBACK_STUBS.get(call_type, "")

        if json_mode and messages:
            last = messages[-1]
            messages = messages[:-1] + [
                {**last, "content": last["content"] + _JSON_INSTRUCTION}
            ]

        lc_messages = _to_langchain_messages(messages)
        model = self._get_model(call_type, routing_override)

        async with self._semaphore:
            response = await retry_async(
                lambda: model.ainvoke(lc_messages),
                is_retryable=is_retryable_http,
            )

        return str(response.content)

    def get_chat_model(
        self,
        call_type: CallType,
        routing_override: dict[str, str] | None = None,
    ) -> BaseChatModel:
        """Return the raw BaseChatModel for a call type — used by LangGraph graph compilation."""
        return self._get_model(call_type, routing_override)

    def _get_model(
        self,
        call_type: CallType,
        routing_override: dict[str, str] | None = None,
    ) -> BaseChatModel:
        override = {CallType(k): v for k, v in routing_override.items()} if routing_override else {}
        model_id = override.get(call_type) or self._routing.get(call_type)
        if not model_id:
            raise KeyError(
                f"No model configured for call type '{call_type}'. "
                f"Check settings.intelligence.routing or workspace_model_routing.config."
            )
        if model_id not in self._model_cache:
            entry = self._catalog.get_model(model_id)
            if entry is None:
                raise KeyError(f"Model '{model_id}' not found in registry.")
            provider = self._vendors.get(entry.vendor)
            if provider is None:
                raise KeyError(f"Vendor '{entry.vendor}' not registered.")
            self._model_cache[model_id] = provider.build_model(entry.vendor_model_id)
        return self._model_cache[model_id]
