"""Router for semantic and structured email search, and autocomplete suggestions."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.analysis import EmailAnalysis
from app.models.email import Email
from app.routers.emails import EmailMetadataResponse
from app.services.ai.embedding import EmbeddingService
from app.services.storage.analysis_repo import AnalysisRepository
from app.services.storage.email_repo import EmailRepository
from app.services.storage.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])
email_repo = EmailRepository()
analysis_repo = AnalysisRepository()
embedding_service = EmbeddingService()


class SearchRequest(BaseModel):
    """Payload representing a hybrid search query."""
    query: str | None = None  # Natural language search query
    account_id: str | None = None
    folder: str | None = None
    sender: str | None = None
    subject_contains: str | None = None
    has_attachments: bool | None = None
    limit: int = 20


@router.post("", response_model=list[EmailMetadataResponse], status_code=status.HTTP_200_OK)
async def search_emails(
    request: SearchRequest,
    session: AsyncSession = Depends(get_db),
) -> list[EmailMetadataResponse]:
    """Execute hybrid semantic vector search or metadata-based SQL query."""
    # 1. Semantic Search Pass
    if request.query:
        # Generate query embedding
        query_vector = await embedding_service.embed_text(request.query)

        # Build ChromaDB where filter
        where_filter = {}
        if request.account_id:
            where_filter["account_id"] = request.account_id
        if request.folder:
            where_filter["folder"] = request.folder
        if request.sender:
            where_filter["sender_email"] = request.sender

        store = ChromaDBStore()
        similar_items = await store.search_similar(
            query_embedding=query_vector,
            n_results=request.limit,
            where=where_filter if where_filter else None,
        )

        email_ids = [item["id"] for item in similar_items]
        if not email_ids:
            return []

        # Fetch emails from DB and preserve ChromaDB order
        stmt = select(Email, EmailAnalysis).outerjoin(
            EmailAnalysis, Email.id == EmailAnalysis.email_id
        ).where(Email.id.in_(email_ids))

        res = await session.execute(stmt)
        rows = res.all()

        row_map = {row[0].id: row for row in rows}
        ordered_rows = [row_map[eid] for eid in email_ids if eid in row_map]

    # 2. Structured SQL Metadata Search Pass
    else:
        stmt = select(Email, EmailAnalysis).outerjoin(
            EmailAnalysis, Email.id == EmailAnalysis.email_id
        )

        if request.account_id:
            stmt = stmt.where(Email.account_id == request.account_id)
        if request.folder:
            stmt = stmt.where(Email.folder == request.folder)
        if request.sender:
            stmt = stmt.where(Email.sender_email.ilike(f"%{request.sender}%"))
        if request.subject_contains:
            stmt = stmt.where(Email.subject.ilike(f"%{request.subject_contains}%"))
        if request.has_attachments is not None:
            stmt = stmt.where(Email.has_attachments == request.has_attachments)

        stmt = stmt.order_by(Email.date.desc()).limit(request.limit)
        res = await session.execute(stmt)
        ordered_rows = res.all()

    # Map results to metadata response list
    results = []
    for email, analysis in ordered_rows:
        import json

        from app.schemas.email import Recipient

        recipients = []
        try:
            if email.recipients_json:
                recipients = [Recipient(**r) for r in json.loads(email.recipients_json)]
        except Exception:
            pass

        results.append(
            EmailMetadataResponse(
                id=email.id,
                account_id=email.account_id,
                thread_id=email.thread_id,
                message_id=email.message_id,
                subject=email.subject,
                sender_name=email.sender_name,
                sender_email=email.sender_email,
                recipients=recipients,
                date=email.date,
                folder=email.folder,
                is_read=email.is_read,
                is_starred=email.is_starred,
                is_important=email.is_important,
                has_attachments=email.has_attachments,
                category=analysis.category if analysis else None,
                priority_score=analysis.priority_score if analysis else None,
                spam_score=analysis.spam_score if analysis else None,
                is_phishing=analysis.is_phishing if analysis else False,
            )
        )
    return results


@router.get("/suggestions", status_code=status.HTTP_200_OK)
async def get_search_suggestions(
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Get autocomplete suggestions for senders and subjects matching the query string."""
    # Senders suggestions
    sender_stmt = (
        select(Email.sender_name, Email.sender_email)
        .where(
            or_(
                Email.sender_name.ilike(f"%{q}%"),
                Email.sender_email.ilike(f"%{q}%")
            )
        )
        .distinct()
        .limit(10)
    )
    sender_res = await session.execute(sender_stmt)
    senders = []
    for name, email in sender_res.all():
        senders.append(f"{name} <{email}>" if name else email)

    # Subject suggestions
    subject_stmt = (
        select(Email.subject)
        .where(Email.subject.ilike(f"%{q}%"))
        .distinct()
        .limit(10)
    )
    subject_res = await session.execute(subject_stmt)
    subjects = [row[0] for row in subject_res.all()]

    return {
        "senders": senders,
        "subjects": subjects,
    }
