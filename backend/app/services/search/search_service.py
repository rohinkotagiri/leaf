"""Search service coordinating query parsing, hybrid searching, result caching, and suggestions."""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email import Email
from app.services.ai.embedding import EmbeddingService
from app.services.search.bm25_searcher import BM25Searcher
from app.services.search.hybrid_searcher import HybridSearcher
from app.services.search.query_parser import QueryParser
from app.services.search.vector_searcher import VectorSearcher
from app.services.storage.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)


class SearchFilters(BaseModel):
    """Explicit parameters passed by the user/UI to restrict search scope."""

    account_id: str | None = None
    limit: int = 20


class SearchResultItem(BaseModel):
    """Represent an individual search hit with relevance scores and snippets."""

    id: str
    thread_id: str | None
    account_id: str
    subject: str
    sender_name: str | None
    sender_email: str
    date: str
    folder: str
    is_read: bool
    is_starred: bool
    is_important: bool
    has_attachments: bool
    category: str | None
    priority_score: float | None
    rrf_score: float
    explanation: str


class SearchResults(BaseModel):
    """Unified wrapper around a list of search result hits with latency metadata."""

    query: str
    results: list[SearchResultItem]
    latency_ms: float
    cached: bool


class SearchCache:
    """Simple LRU Cache for search queries."""

    def __init__(self, maxsize: int = 50) -> None:
        self.maxsize = maxsize
        self._cache: dict[tuple[Any, ...], Any] = {}
        self._keys: list[tuple[Any, ...]] = []

    def get(self, key: tuple[Any, ...]) -> Any | None:
        if key in self._cache:
            self._keys.remove(key)
            self._keys.append(key)
            return self._cache[key]
        return None

    def set(self, key: tuple[Any, ...], value: Any) -> None:
        if key in self._cache:
            self._keys.remove(key)
        elif len(self._cache) >= self.maxsize:
            oldest = self._keys.pop(0)
            del self._cache[oldest]
        self._cache[key] = value
        self._keys.append(key)

    def clear(self) -> None:
        self._cache.clear()
        self._keys.clear()


class SearchService:
    """Unified coordinator for natural language query search, autocomplete suggestions, and cache."""

    def __init__(
        self,
        *,
        query_parser: QueryParser | None = None,
        bm25_searcher: BM25Searcher | None = None,
        vector_searcher: VectorSearcher | None = None,
        hybrid_searcher: HybridSearcher | None = None,
    ) -> None:
        self.query_parser = query_parser or QueryParser()
        self.bm25_searcher = bm25_searcher or BM25Searcher()
        self.vector_searcher = vector_searcher or VectorSearcher(
            embedding_service=EmbeddingService(),
            vector_store=ChromaDBStore(),
        )
        self.hybrid_searcher = hybrid_searcher or HybridSearcher(
            bm25_searcher=self.bm25_searcher,
            vector_searcher=self.vector_searcher,
        )
        self.cache = SearchCache(maxsize=50)

    async def search(
        self,
        query: str,
        filters: SearchFilters,
        session: AsyncSession,
    ) -> SearchResults:
        """Run the full search pipeline: parse query, hybrid search RRF, DB mapping, and caching."""
        start_time = time.perf_counter()
        query_strip = query.strip()

        # Cache key based on query, account_id, limit
        cache_key = (query_strip, filters.account_id, filters.limit)

        # Check Cache
        cached_results = self.cache.get(cache_key)
        if cached_results is not None:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info("Search Cache Hit for query: '%s' (Latency: %.2fms)", query_strip, latency_ms)
            return SearchResults(
                query=query_strip,
                results=cached_results,
                latency_ms=latency_ms,
                cached=True,
            )

        # 1. Initialize BM25 searcher if not initialized
        await self.bm25_searcher.initialize(session)

        # 2. Parse natural language query
        parsed_query = await self.query_parser.parse(query_strip)

        # 3. Perform hybrid BM25 and vector semantic search
        hits = await self.hybrid_searcher.search(
            query=query_strip,
            parsed_query=parsed_query,
            session=session,
            account_id=filters.account_id,
            limit=filters.limit,
        )

        # 4. Map hit dictionaries to SearchResultItem objects
        results_list = []
        for hit in hits:
            email = hit["email"]
            analysis = hit["analysis"]

            results_list.append(
                SearchResultItem(
                    id=email.id,
                    thread_id=email.thread_id,
                    account_id=email.account_id,
                    subject=email.subject or "",
                    sender_name=email.sender_name,
                    sender_email=email.sender_email,
                    date=email.date.isoformat(),
                    folder=email.folder or "",
                    is_read=email.is_read,
                    is_starred=email.is_starred,
                    is_important=email.is_important,
                    has_attachments=email.has_attachments,
                    category=analysis.category if analysis else None,
                    priority_score=analysis.priority_score if analysis else None,
                    rrf_score=hit["rrf_score"],
                    explanation=hit["explanation"],
                )
            )

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "Search executed for query: '%s' - results: %d (Latency: %.2fms)",
            query_strip,
            len(results_list),
            latency_ms,
        )

        # Store in cache
        self.cache.set(cache_key, results_list)

        return SearchResults(
            query=query_strip,
            results=results_list,
            latency_ms=latency_ms,
            cached=False,
        )

    async def get_query_suggestions(
        self,
        session: AsyncSession,
        account_id: str | None = None,
    ) -> dict[str, list[str]]:
        """Get suggestions for most frequent senders, recent subjects, and recommended searches."""
        # 1. Frequent Senders
        sender_stmt = (
            select(Email.sender_name, Email.sender_email, func.count(Email.id).label("cnt"))
            .group_by(Email.sender_email)
        )
        if account_id:
            sender_stmt = sender_stmt.where(Email.account_id == account_id)

        sender_stmt = sender_stmt.order_by(func.count(Email.id).desc()).limit(5)
        sender_res = await session.execute(sender_stmt)

        senders = []
        for name, email, _ in sender_res.all():
            senders.append(f"{name} <{email}>" if name else email)

        # 2. Recent Subjects
        subj_stmt = select(Email.subject).distinct()
        if account_id:
            subj_stmt = subj_stmt.where(Email.account_id == account_id)

        subj_stmt = subj_stmt.order_by(Email.date.desc()).limit(5)
        subj_res = await session.execute(subj_stmt)
        subjects = [row[0] for row in subj_res.all() if row[0]]

        # 3. Saved / Recommended searches
        recommended = [
            "unread emails from last week",
            "emails with attachments from work",
            "yesterday emails about work",
            "travel emails from last 3 months",
            "internship applications",
        ]

        return {
            "senders": senders,
            "subjects": subjects,
            "recommended": recommended,
        }
