from __future__ import annotations

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
