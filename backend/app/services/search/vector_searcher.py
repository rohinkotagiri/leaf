"""Vector search engine wrapper around ChromaDB and embedding services."""

from __future__ import annotations

import logging
from typing import Any

from app.services.ai.embedding import EmbeddingService
from app.services.storage.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)


class VectorSearcher:
    """Performs semantic similarity search against stored email embeddings in ChromaDB."""

    def __init__(
        self,
        *,
        embedding_service: EmbeddingService | None = None,
        vector_store: ChromaDBStore | None = None,
    ) -> None:
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or ChromaDBStore()

    async def search(
        self,
        query: str,
        account_id: str | None = None,
        folder: str | None = None,
        sender_email: str | None = None,
        has_attachments: bool | None = None,
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """Embed the query and query ChromaDB with matching metadata filters.

        Returns:
            List of dicts with keys: 'id', 'score' (converted similarity from distance), and 'metadata'.
        """
        # Generate query embedding
        query_vector = await self.embedding_service.embed_text(query)

        # Build ChromaDB metadata filters
        conditions: list[dict[str, Any]] = []

        if account_id:
            conditions.append({"account_id": account_id})
        if folder:
            conditions.append({"folder": folder})
        if sender_email:
            conditions.append({"sender_email": sender_email})
        if has_attachments is not None:
            conditions.append({"has_attachments": has_attachments})

        where_filter: dict[str, Any] | None = None
        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        # Query ChromaDB
        similar_items = await self.vector_store.search_similar(
            query_embedding=query_vector,
            n_results=top_k,
            where=where_filter,
        )

        results = []
        for item in similar_items:
            # Convert cosine distance to a similarity score where higher is better.
            # ChromaDB cosine distance ranges from 0 to 2 (0 being identical, 1 orthogonal, 2 opposite).
            # We can use: score = 1.0 - (distance / 2.0) or simply convert distance to score.
            dist = item.get("distance")
            score = 1.0 - (dist / 2.0) if dist is not None else 0.0

            results.append({
                "id": item["id"],
                "score": max(0.0, min(1.0, score)),
                "metadata": item.get("metadata", {}),
            })

        return results
