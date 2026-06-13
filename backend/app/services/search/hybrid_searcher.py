"""Hybrid search engine combining BM25 keyword and vector semantic search using Reciprocal Rank Fusion."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import EmailAnalysis
from app.models.email import Email
from app.services.search.bm25_searcher import BM25Searcher
from app.services.search.query_parser import ParsedQuery
from app.services.search.vector_searcher import VectorSearcher

logger = logging.getLogger(__name__)


class HybridSearcher:
    """Orchestrates parallel keyword (BM25) and semantic (Vector) search.

    Combines results via Reciprocal Rank Fusion (RRF).
    """

    def __init__(
        self,
        bm25_searcher: BM25Searcher,
        vector_searcher: VectorSearcher,
        rrf_constant: float = 60.0,
    ) -> None:
        self.bm25_searcher = bm25_searcher
        self.vector_searcher = vector_searcher
        self.rrf_constant = rrf_constant

    async def search(
        self,
        query: str,
        parsed_query: ParsedQuery,
        session: AsyncSession,
        account_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Run BM25 and vector search in parallel, merge with RRF, and filter via database."""
        has_query_text = bool(parsed_query.keywords)

        if not has_query_text:
            return await self._search_pure_metadata(session, parsed_query, account_id, limit)

        # 2. Parallel keyword and vector searches
        # Gather search text
        search_text = " ".join(parsed_query.keywords)

        bm25_task = self.bm25_searcher.search(search_text, top_k=100)
        vector_task = self.vector_searcher.search(
            query=search_text,
            account_id=account_id,
            sender_email=parsed_query.sender_filter,
            has_attachments=parsed_query.has_attachments,
            top_k=100,
        )

        bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)

        # 3. Reciprocal Rank Fusion (RRF)
        # Compute RRF score: score = sum(1 / (k + rank))
        rrf_scores: dict[str, float] = {}
        bm25_ranks: dict[str, int] = {}
        vector_ranks: dict[str, int] = {}

        for rank, item in enumerate(bm25_results, start=1):
            eid = item["id"]
            bm25_ranks[eid] = rank
            rrf_scores[eid] = rrf_scores.get(eid, 0.0) + (1.0 / (self.rrf_constant + rank))

        for rank, item in enumerate(vector_results, start=1):
            eid = item["id"]
            vector_ranks[eid] = rank
            rrf_scores[eid] = rrf_scores.get(eid, 0.0) + (1.0 / (self.rrf_constant + rank))

        if not rrf_scores:
            return []

        # Sort candidate IDs by descending RRF score
        sorted_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        candidate_ids = [eid for eid, _ in sorted_candidates]

        # 4. Fetch from database while applying remaining structured filters
        stmt = select(Email, EmailAnalysis).outerjoin(
            EmailAnalysis, Email.id == EmailAnalysis.email_id
        ).where(Email.id.in_(candidate_ids))

        # Apply parsed filters
        if account_id:
            stmt = stmt.where(Email.account_id == account_id)
        if parsed_query.sender_filter:
            stmt = stmt.where(
                (Email.sender_email.ilike(f"%{parsed_query.sender_filter}%")) |
                (Email.sender_name.ilike(f"%{parsed_query.sender_filter}%"))
            )
        if parsed_query.category_filter:
            stmt = stmt.where(EmailAnalysis.category == parsed_query.category_filter)
        if parsed_query.has_attachments is not None:
            stmt = stmt.where(Email.has_attachments == parsed_query.has_attachments)
        if parsed_query.is_unread is not None:
            stmt = stmt.where(Email.is_read == (not parsed_query.is_unread))
        if parsed_query.date_from:
            stmt = stmt.where(Email.date >= datetime.strptime(parsed_query.date_from, "%Y-%m-%d"))
        if parsed_query.date_to:
            to_date = datetime.strptime(parsed_query.date_to, "%Y-%m-%d") + timedelta(days=1)
            stmt = stmt.where(Email.date < to_date)

        res = await session.execute(stmt)
        matched_rows = res.all()

        # Build a fast map of email_id -> (Email, EmailAnalysis)
        row_map = {row[0].id: row for row in matched_rows}

        # Keep original RRF order, map into final list of results with match explanation snippet
        results = []
        for eid, score in sorted_candidates:
            if eid not in row_map:
                continue

            email, analysis = row_map[eid]
            is_bm25 = eid in bm25_ranks
            is_vector = eid in vector_ranks

            # Explanation snippets
            if is_bm25 and is_vector:
                explanation = f"Combined match (Keyword rank: {bm25_ranks[eid]}, Semantic rank: {vector_ranks[eid]})"
            elif is_bm25:
                explanation = f"Keyword match (BM25 rank: {bm25_ranks[eid]})"
            else:
                explanation = f"Semantic match (Vector rank: {vector_ranks[eid]})"

            results.append({
                "email": email,
                "analysis": analysis,
                "rrf_score": score,
                "explanation": explanation,
            })

        return results[:limit]

    async def _search_pure_metadata(
        self,
        session: AsyncSession,
        parsed_query: ParsedQuery,
        account_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fallback to database queries when query has only structured metadata filters."""
        stmt = select(Email, EmailAnalysis).outerjoin(
            EmailAnalysis, Email.id == EmailAnalysis.email_id
        )

        if account_id:
            stmt = stmt.where(Email.account_id == account_id)
        if parsed_query.sender_filter:
            stmt = stmt.where(
                (Email.sender_email.ilike(f"%{parsed_query.sender_filter}%")) |
                (Email.sender_name.ilike(f"%{parsed_query.sender_filter}%"))
            )
        if parsed_query.category_filter:
            stmt = stmt.where(EmailAnalysis.category == parsed_query.category_filter)
        if parsed_query.has_attachments is not None:
            stmt = stmt.where(Email.has_attachments == parsed_query.has_attachments)
        if parsed_query.is_unread is not None:
            stmt = stmt.where(Email.is_read == (not parsed_query.is_unread))
        if parsed_query.date_from:
            stmt = stmt.where(Email.date >= datetime.strptime(parsed_query.date_from, "%Y-%m-%d"))
        if parsed_query.date_to:
            to_date = datetime.strptime(parsed_query.date_to, "%Y-%m-%d") + timedelta(days=1)
            stmt = stmt.where(Email.date < to_date)

        # Sort by priority score first, then by date desc
        stmt = stmt.order_by(EmailAnalysis.priority_score.desc(), Email.date.desc()).limit(limit)

        res = await session.execute(stmt)
        rows = res.all()

        results = []
        for email, analysis in rows:
            results.append({
                "email": email,
                "analysis": analysis,
                "rrf_score": 1.0,
                "explanation": "Structured metadata match",
            })

        return results
