"""ChromaDB vector store — wraps ChromaDB for email embedding storage.

Stores only email_id + lightweight metadata in ChromaDB.
Full email content lives in SQLite — never in vector store metadata
(ChromaDB has a 41KB metadata limit).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import chromadb

from app.config import settings

logger = logging.getLogger(__name__)

# Metadata fields safe to store in ChromaDB (small, filterable)
ALLOWED_METADATA_KEYS = {
    "account_id",
    "folder",
    "sender_email",
    "date_iso",
    "subject_short",
    "has_attachments",
}


class ChromaDBStore:
    """Wrapper around ChromaDB for email embedding storage.

    All ChromaDB operations are synchronous, so we wrap them in
    asyncio.to_thread() for async compatibility.
    """

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str = "emails",
    ) -> None:
        self._persist_dir = persist_dir or settings.CHROMA_PERSIST_DIR
        self._collection_name = collection_name
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    def _ensure_initialized(self) -> chromadb.Collection:
        """Lazily initialize the ChromaDB client and collection."""
        if self._collection is None:
            Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self._persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "ChromaDB collection '%s' initialized at %s (%d vectors)",
                self._collection_name,
                self._persist_dir,
                self._collection.count(),
            )
        return self._collection

    def _sanitize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Filter metadata to only allowed keys and safe types."""
        sanitized: dict[str, Any] = {}
        for key in ALLOWED_METADATA_KEYS:
            if key in metadata:
                val = metadata[key]
                # ChromaDB only supports str, int, float, bool in metadata
                if isinstance(val, (str, int, float, bool)):
                    sanitized[key] = val
        return sanitized

    # ── Write operations ──────────────────────────────────────────────

    async def add_embedding(
        self,
        email_id: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a single embedding with its email_id and metadata."""

        def _add() -> None:
            collection = self._ensure_initialized()
            safe_meta = self._sanitize_metadata(metadata or {})
            collection.upsert(
                ids=[email_id],
                embeddings=[embedding],
                metadatas=[safe_meta] if safe_meta else None,
            )

        await asyncio.to_thread(_add)
        logger.debug("Added embedding for email %s", email_id[:12])

    async def add_embeddings_bulk(
        self,
        items: list[dict[str, Any]],
    ) -> int:
        """Batch add embeddings.

        Each item should have keys: 'id', 'embedding', and optionally 'metadata'.

        Returns:
            Number of embeddings added.
        """
        if not items:
            return 0

        def _bulk_add() -> int:
            collection = self._ensure_initialized()
            ids = [item["id"] for item in items]
            embeddings = [item["embedding"] for item in items]
            metadatas = [
                self._sanitize_metadata(item.get("metadata", {}))
                for item in items
            ]
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas if any(metadatas) else None,
            )
            return len(ids)

        count = await asyncio.to_thread(_bulk_add)
        logger.info("Bulk added %d embeddings", count)
        return count

    # ── Read operations ───────────────────────────────────────────────

    async def search_similar(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar emails by embedding.

        Args:
            query_embedding: The query vector.
            n_results: Number of results to return.
            where: Optional ChromaDB where filter (e.g. {"folder": "INBOX"}).

        Returns:
            List of dicts with keys: 'id', 'distance', 'metadata'.
        """

        def _search() -> list[dict[str, Any]]:
            collection = self._ensure_initialized()
            kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": min(n_results, collection.count() or 1),
            }
            if where:
                kwargs["where"] = where

            results = collection.query(**kwargs)

            output: list[dict[str, Any]] = []
            if results and results["ids"]:
                for i, eid in enumerate(results["ids"][0]):
                    output.append(
                        {
                            "id": eid,
                            "distance": (
                                results["distances"][0][i]
                                if results.get("distances")
                                else None
                            ),
                            "metadata": (
                                results["metadatas"][0][i]
                                if results.get("metadatas")
                                else {}
                            ),
                        }
                    )
            return output

        return await asyncio.to_thread(_search)

    # ── Delete operations ─────────────────────────────────────────────

    async def delete_by_id(self, email_id: str) -> None:
        """Delete an embedding by email ID."""

        def _delete() -> None:
            collection = self._ensure_initialized()
            collection.delete(ids=[email_id])

        await asyncio.to_thread(_delete)
        logger.debug("Deleted embedding for email %s", email_id[:12])

    async def delete_by_ids(self, email_ids: list[str]) -> None:
        """Batch delete embeddings by email IDs."""
        if not email_ids:
            return

        def _delete() -> None:
            collection = self._ensure_initialized()
            collection.delete(ids=email_ids)

        await asyncio.to_thread(_delete)
        logger.debug("Deleted %d embeddings", len(email_ids))

    # ── Stats ─────────────────────────────────────────────────────────

    async def get_collection_stats(self) -> dict[str, Any]:
        """Get statistics about the ChromaDB collection."""

        def _stats() -> dict[str, Any]:
            collection = self._ensure_initialized()
            return {
                "collection_name": collection.name,
                "count": collection.count(),
                "persist_dir": self._persist_dir,
            }

        return await asyncio.to_thread(_stats)
