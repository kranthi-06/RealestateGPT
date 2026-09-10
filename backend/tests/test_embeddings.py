"""Tests for validated embedding-provider responses."""

import httpx

from app.ai.embeddings import EmbeddingService


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"data": [{"embedding": [3.0, 4.0]}]}


def test_openai_embedding_response_is_normalized(monkeypatch) -> None:
    service = EmbeddingService()
    service._provider = "openai"

    monkeypatch.setattr("app.ai.embeddings.settings.AI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _Response())

    assert service._embed_openai("near metro") == [0.6, 0.8]
