"""In-memory BM25 search engine for keyword searches across email subjects and bodies."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email import Email

logger = logging.getLogger(__name__)


def tokenize_text(text: str) -> list[str]:
    """Lowercase text and split into clean alphanumeric tokens."""
    if not text:
        return []
    return re.findall(r'\b\w+\b', text.lower())


class BM25Searcher:
    """In-memory keyword search engine based on BM25Okapi.

    Lazily loaded and rebuilt from the SQLite DB.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._bm25: BM25Okapi | None = None
        self._doc_ids: list[str] = []
        self._corpus_texts: dict[str, tuple[str, str]] = {}  # email_id -> (subject, body)
        self._is_initialized = False

    async def initialize(self, session: AsyncSession) -> None:
        """Fetch all stored emails and construct the initial BM25 index."""
        async with self._lock:
            if self._is_initialized:
                return

            logger.info("Initializing BM25Searcher index...")
            stmt = select(Email.id, Email.subject, Email.body_text)
            result = await session.execute(stmt)
            emails = result.all()

            corpus_tokens: list[list[str]] = []
            doc_ids: list[str] = []
            corpus_texts: dict[str, tuple[str, str]] = {}

            for eid, subject, body in emails:
                subj_clean = subject or ""
                body_clean = body or ""
                combined_text = f"{subj_clean} {body_clean}"
                tokens = tokenize_text(combined_text)
                corpus_tokens.append(tokens)
                doc_ids.append(eid)
                corpus_texts[eid] = (subj_clean, body_clean)

            if corpus_tokens:
                self._bm25 = BM25Okapi(corpus_tokens)
            else:
                self._bm25 = None

            self._doc_ids = doc_ids
            self._corpus_texts = corpus_texts
            self._is_initialized = True
            logger.info("BM25Searcher initialized with %d indexed emails", len(doc_ids))

    async def update_email(self, email_id: str, subject: str, body: str) -> None:
        """Add or update a single email in the index and rebuild the BM25 index."""
        async with self._lock:
            if not self._is_initialized:
                # Will be initialized properly when first queried
                return

            subj_clean = subject or ""
            body_clean = body or ""
            self._corpus_texts[email_id] = (subj_clean, body_clean)

            # Rebuild index from current corpus_texts mapping
            corpus_tokens: list[list[str]] = []
            doc_ids: list[str] = []

            for eid, (subj, bdy) in self._corpus_texts.items():
                combined = f"{subj} {bdy}"
                corpus_tokens.append(tokenize_text(combined))
                doc_ids.append(eid)

            if corpus_tokens:
                self._bm25 = BM25Okapi(corpus_tokens)
            else:
                self._bm25 = None

            self._doc_ids = doc_ids
            logger.debug("BM25Searcher updated index for email %s", email_id[:12])

    async def delete_emails(self, email_ids: list[str]) -> None:
        """Delete emails from the index."""
        async with self._lock:
            if not self._is_initialized:
                return

            updated = False
            for eid in email_ids:
                if eid in self._corpus_texts:
                    del self._corpus_texts[eid]
                    updated = True

            if updated:
                corpus_tokens: list[list[str]] = []
                doc_ids: list[str] = []
                for eid, (subj, bdy) in self._corpus_texts.items():
                    combined = f"{subj} {bdy}"
                    corpus_tokens.append(tokenize_text(combined))
                    doc_ids.append(eid)

                if corpus_tokens:
                    self._bm25 = BM25Okapi(corpus_tokens)
                else:
                    self._bm25 = None

                self._doc_ids = doc_ids
                logger.debug("BM25Searcher removed %d emails from index", len(email_ids))

    async def search(self, query: str, top_k: int = 50) -> list[dict[str, Any]]:
        """Search the indexed emails using BM25 and return ranked scored results."""
        if not self._is_initialized or not self._bm25:
            return []

        tokens = tokenize_text(query)
        if not tokens:
            return []

        # Get scores synchronously
        scores = self._bm25.get_scores(tokens)

        results = []
        for i, score in enumerate(scores):
            if score > 0.0:
                results.append({
                    "id": self._doc_ids[i],
                    "score": float(score)
                })

        # Sort descending by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
