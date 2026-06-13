"""Router for semantic and structured hybrid search, and autocomplete suggestions."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.analysis import EmailAnalysis
from app.models.email import Email
from app.routers.emails import EmailMetadataResponse
from app.schemas.email import Recipient
from app.services.search.search_service import SearchFilters, SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])
search_service = SearchService()


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
    """Execute hybrid semantic vector search, natural language search, or metadata-based SQL query."""
    # If a query is provided, we route it through the Hybrid SearchService
    if request.query and request.query.strip():
        search_res = await search_service.search(
            query=request.query,
            filters=SearchFilters(
                account_id=request.account_id,
                limit=request.limit,
            ),
            session=session,
        )

        # Map list of hits to EmailMetadataResponse
        results = []
        # Since SearchService might return cached SearchResultItems, let's map them
        for item in search_res.results:
            # Senders and recipients are mapped. We need to fetch email to ensure message_id or just build it
            stmt = select(Email, EmailAnalysis).outerjoin(
                EmailAnalysis, Email.id == EmailAnalysis.email_id
            ).where(Email.id == item.id)
            res = await session.execute(stmt)
            row = res.first()
            if not row:
                continue
            email, analysis = row

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
                    category=item.category,
                    priority_score=item.priority_score,
                    spam_score=analysis.spam_score if analysis else None,
                    is_phishing=analysis.is_phishing if analysis else False,
                )
            )
        return results

    # 2. Structured SQL Metadata Search Pass / Empty Query Fallback
    else:
        stmt = select(Email, EmailAnalysis).outerjoin(
            EmailAnalysis, Email.id == EmailAnalysis.email_id
        )

        if request.account_id:
            stmt = stmt.where(Email.account_id == request.account_id)
        if request.folder:
            stmt = stmt.where(Email.folder == request.folder)
        if request.sender:
            stmt = stmt.where(
                (Email.sender_email.ilike(f"%{request.sender}%")) |
                (Email.sender_name.ilike(f"%{request.sender}%"))
            )
        if request.subject_contains:
            stmt = stmt.where(Email.subject.ilike(f"%{request.subject_contains}%"))
        if request.has_attachments is not None:
            stmt = stmt.where(Email.has_attachments == request.has_attachments)

        # Default fallback: If empty query (no folder specified), prioritize INBOX, else use folder
        if not request.folder:
            # Only return INBOX emails if no folder specified to represent "inbox sorted by priority"
            stmt = stmt.where(Email.folder == "INBOX")

        # Sort by priority score first, then by date descending
        stmt = stmt.order_by(
            EmailAnalysis.priority_score.desc().nullslast(),
            Email.date.desc()
        ).limit(request.limit)

        res = await session.execute(stmt)
        ordered_rows = res.all()

        results = []
        for email, analysis in ordered_rows:
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
    account_id: str | None = Query(None),
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
    )
    if account_id:
        sender_stmt = sender_stmt.where(Email.account_id == account_id)

    sender_stmt = sender_stmt.distinct().limit(10)
    sender_res = await session.execute(sender_stmt)
    senders = []
    for name, email in sender_res.all():
        senders.append(f"{name} <{email}>" if name else email)

    # Subject suggestions
    subject_stmt = (
        select(Email.subject)
        .where(Email.subject.ilike(f"%{q}%"))
    )
    if account_id:
        subject_stmt = subject_stmt.where(Email.account_id == account_id)

    subject_stmt = subject_stmt.distinct().limit(10)
    subject_res = await session.execute(subject_stmt)
    subjects = [row[0] for row in subject_res.all() if row[0]]

    # Recommendations
    rec_suggestions = await search_service.get_query_suggestions(session, account_id)

    return {
        "senders": senders,
        "subjects": subjects,
        "recommended": rec_suggestions["recommended"],
    }
