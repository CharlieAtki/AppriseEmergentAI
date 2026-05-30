from __future__ import annotations

import asyncio

from fastembed import TextEmbedding

from core.config import settings

_encoder: TextEmbedding | None = None


def get_encoder() -> TextEmbedding:
    global _encoder
    if _encoder is None:
        _encoder = TextEmbedding(settings.memory.embedding_model)
    return _encoder


def embed(text: str) -> list[float]:
    return next(get_encoder().embed([text])).tolist()


async def aembed(text: str) -> list[float]:
    return await asyncio.to_thread(embed, text)
