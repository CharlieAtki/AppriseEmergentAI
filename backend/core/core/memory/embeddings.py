from __future__ import annotations

import asyncio

from sentence_transformers import SentenceTransformer

from core.config import settings

_encoder: SentenceTransformer | None = None


def get_encoder() -> SentenceTransformer:
    global _encoder
    if _encoder is None:
        _encoder = SentenceTransformer(settings.memory.embedding_model)
    return _encoder


def embed(text: str) -> list[float]:
    return get_encoder().encode(text, normalize_embeddings=True).tolist()


async def aembed(text: str) -> list[float]:
    return await asyncio.to_thread(embed, text)
