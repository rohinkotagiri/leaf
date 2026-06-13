"""Embedding service backed by Ollama."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.ai.client import OllamaClient
from app.services.ai.utils import chunks, response_embeddings, truncate_tokens


class EmbeddingService:
    """Generate embeddings for email text with fixed preprocessing."""

    MAX_BATCH_SIZE = 32
    MAX_TOKENS = 512

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.client = client or OllamaClient()
        self.model = model or settings.OLLAMA_EMBED_MODEL
        self.timeout = timeout or float(settings.OLLAMA_FAST_TIMEOUT)

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        embeddings = await self.embed_batch([text])
        return embeddings[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in max-32 batches while preserving input order."""
        if not texts:
            return []

        processed = [truncate_tokens(text, self.MAX_TOKENS) for text in texts]
        output: list[list[float]] = []
        for batch in chunks(processed, self.MAX_BATCH_SIZE):
            response = await self.client.embed(
                model=self.model,
                input=batch,
                timeout=self.timeout,
            )
            embeddings = response_embeddings(response)
            if len(embeddings) != len(batch):
                raise ValueError("Ollama returned a different embedding count than requested")
            output.extend(embeddings)
        return output
