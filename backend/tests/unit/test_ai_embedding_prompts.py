"""Unit tests for prompt registry and embeddings."""

from __future__ import annotations

import pytest

from app.services.ai.embedding import EmbeddingService
from app.services.ai.mock_client import MockOllamaClient
from app.services.ai.prompts import PromptRegistry


def test_prompt_registry_returns_versioned_prompt() -> None:
    prompt = PromptRegistry.get(PromptRegistry.CLASSIFY_V1)

    assert prompt.version == "classify_v1"
    rendered = prompt.render(
        categories="work, other",
        few_shot_examples="No examples",
        subject="Status",
        sender="alice@example.com",
        body_preview="Please review",
    )
    assert "Status" in rendered
    assert "work, other" in rendered


@pytest.mark.asyncio
async def test_embed_batch_splits_at_32_and_preserves_order() -> None:
    client = MockOllamaClient(embedding_dimensions=4)
    service = EmbeddingService(client=client)

    embeddings = await service.embed_batch(["test"] * 100)

    assert len(embeddings) == 100
    assert all(len(vector) == 4 for vector in embeddings)
    assert len(client.embed_calls) == 4
    assert [len(call["input"]) for call in client.embed_calls] == [32, 32, 32, 4]


@pytest.mark.asyncio
async def test_embedding_preprocesses_to_512_tokens() -> None:
    client = MockOllamaClient()
    service = EmbeddingService(client=client)
    long_text = " ".join(f"word{i}" for i in range(700))

    await service.embed_text(long_text)

    sent_text = client.embed_calls[0]["input"][0]
    assert len(sent_text.split()) == 512
    assert "word699" not in sent_text
