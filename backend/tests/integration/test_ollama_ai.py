"""Integration tests for real Ollama-backed AI services."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.config import settings
from app.services.ai.classification import ClassificationService
from app.services.ai.client import OllamaClient, OllamaModelUnavailableError
from app.services.ai.embedding import EmbeddingService
from app.services.ai.summarization import SummarizationService


@pytest_asyncio.fixture
async def real_ollama_client() -> OllamaClient:
    client = OllamaClient(max_retries=0)
    if not await client.is_running():
        pytest.skip("Ollama is not running")

    for model in (
        settings.OLLAMA_FAST_MODEL,
        settings.OLLAMA_CHAT_MODEL,
        settings.OLLAMA_EMBED_MODEL,
    ):
        try:
            await client.ensure_model_available(model)
        except OllamaModelUnavailableError:
            pytest.skip(f"Ollama model {model!r} is not available")
    return client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_ollama_embedding_and_classification(real_ollama_client: OllamaClient) -> None:
    embedding = await EmbeddingService(client=real_ollama_client).embed_text("test")
    assert embedding
    assert all(isinstance(value, float) for value in embedding)

    result = await ClassificationService(client=real_ollama_client).classify_email(
        "Quarterly report",
        "alice@example.com",
        "Please send the quarterly report by Friday afternoon.",
    )
    assert result.category
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_ollama_summarization(real_ollama_client: OllamaClient) -> None:
    summary = await SummarizationService(client=real_ollama_client).summarize_email(
        "Planning notes",
        "bob@example.com",
        "We agreed to meet Monday, review the launch checklist, and assign owners.",
    )
    assert summary.strip()
