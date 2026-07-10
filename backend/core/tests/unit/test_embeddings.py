from __future__ import annotations

import threading
import time
from unittest.mock import patch

import core.memory.embeddings as embeddings_module
from core.memory.embeddings import get_encoder


class TestGetEncoder:
    def test_caches_encoder_across_calls(self) -> None:
        embeddings_module._encoder = None
        try:
            with patch.object(embeddings_module, "TextEmbedding") as mock_text_embedding:
                first = get_encoder()
                second = get_encoder()

                assert first is second
                mock_text_embedding.assert_called_once_with(
                    embeddings_module.settings.memory.embedding_model
                )
        finally:
            embeddings_module._encoder = None

    def test_caches_encoder_across_concurrent_calls(self) -> None:
        embeddings_module._encoder = None
        try:
            with patch.object(embeddings_module, "TextEmbedding") as mock_text_embedding:
                # Simulate slow construction to widen the race window between
                # the None check and the assignment.
                mock_text_embedding.side_effect = lambda *a, **kw: time.sleep(0.01) or object()

                results: list[object] = []

                def call_get_encoder() -> None:
                    results.append(get_encoder())

                threads = [threading.Thread(target=call_get_encoder) for _ in range(20)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                assert len(results) == 20
                assert len({id(result) for result in results}) == 1
                mock_text_embedding.assert_called_once_with(
                    embeddings_module.settings.memory.embedding_model
                )
        finally:
            embeddings_module._encoder = None
