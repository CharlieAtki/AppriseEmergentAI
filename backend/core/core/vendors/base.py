from __future__ import annotations

from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel


class VendorProvider(ABC):
    """Contract every vendor adapter must fulfil.

    Implementations live in their own package (anthropic/, azure/, aws/, ollama/).
    All vendor-specific credential handling, client setup, and retry config
    belongs inside the subclass — nothing leaks out through this interface.
    """

    @property
    @abstractmethod
    def vendor_name(self) -> str:
        """Machine-readable vendor identifier, e.g. 'anthropic', 'azure'."""

    @abstractmethod
    def build_model(self, model_id: str, **kwargs: object) -> BaseChatModel:
        """Return a configured BaseChatModel for the given vendor-internal model_id.

        model_id is the vendor's own identifier (e.g. 'claude-haiku-4-5-20251001'),
        not the registry key ('anthropic/claude-haiku-4-5-20251001').
        """
