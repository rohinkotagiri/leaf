"""Router for email retrieval, updates, thread gathering, and AI summarization."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.analysis import EmailAnalysis
from app.models.email import Email
from app.schemas.analysis import AnalysisResponse
from app.schemas.email import Recipient
from app.services.pipeline import AnalysisPipeline
from app.services.storage.analysis_repo import AnalysisRepository
from app.services.storage.email_repo import EmailRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/emails", tags=["emails"])
email_repo = EmailRepository()
analysis_repo = AnalysisRepository()


class EmailMetadataResponse(BaseModel):
    """Sleek, lightweight response for email list view (no body content)."""
    id: str
    account_id: str
    thread_id: str | None
    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    recipients: list[Recipient]
    date: datetime | None
    folder: str
    is_read: bool
    is_starred: bool
    is_important: bool
    has_attachments: bool
    category: str | None = None
    priority_score: float | None = None
    spam_score: float | None = None
    is_phishing: bool = False

    model_config = {"from_attributes": True}


class EmailDetailResponse(BaseModel):
    """Detailed response for single email viewing, including body text and AI analysis."""
    id: str
    account_id: str
    thread_id: str | None
    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    recipients: list[Recipient]
    date: datetime | None
    body_text: str
    body_html: str
    folder: str
    is_read: bool
    is_starred: bool
    is_important: bool
    has_attachments: bool
    attachment_names: list[str]
    analysis: AnalysisResponse | None = None

    model_config = {"from_attributes": True}


class EmailUpdateRequest(BaseModel):
    """Payload to patch email flags/labels."""
    is_read: bool | None = None
    is_starred: bool | None = None
    is_important: bool | None = None
    labels: list[str] | None = None


class EmailActionRequest(BaseModel):
    """Payload for bulk/single email operations."""
    action: Literal["archive", "delete", "mark_important"]


def email_to_detail_response(email: Email, analysis: EmailAnalysis | None) -> EmailDetailResponse:
    """Convert DB entities to EmailDetailResponse."""
    recipients = []
    try:
        if email.recipients_json:
            recipients = [Recipient(**r) for r in json.loads(email.recipients_json)]
    except Exception:
        logger.warning("Failed to parse recipients_json for email %s", email.id)

    attachments = []
    try:
        if email.attachment_names:
            attachments = json.loads(email.attachment_names)
    except Exception:
        logger.warning("Failed to parse attachment_names for email %s", email.id)

    analysis_res = None
    if analysis:
        analysis_res = AnalysisResponse.model_validate(analysis)

    return EmailDetailResponse(
        id=email.id,
        account_id=email.account_id,
        thread_id=email.thread_id,
        message_id=email.message_id,
        subject=email.subject,
        sender_name=email.sender_name,
        sender_email=email.sender_email,
        recipients=recipients,
        date=email.date,
        body_text=email.body_text,
        body_html=email.body_html,
        folder=email.folder,
        is_read=email.is_read,
        is_starred=email.is_starred,
        is_important=email.is_important,
        has_attachments=email.has_attachments,
        attachment_names=attachments,
        analysis=analysis_res,
    )


@router.get("", response_model=dict[str, Any], status_code=status.HTTP_200_OK)
async def list_emails(
    account_id: str | None = None,
    folder: str | None = None,
    category: str | None = None,
    is_read: bool | None = None,
    priority_min: float | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    after: str | None = Query(None, description="Cursor: email_id of the last item in the previous page"),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve emails using cursor-based pagination and flexible search criteria."""
    stmt = select(Email, EmailAnalysis).outerjoin(
        EmailAnalysis, Email.id == EmailAnalysis.email_id
    )

    # Apply filters
    if account_id:
        stmt = stmt.where(Email.account_id == account_id)
    if folder:
        stmt = stmt.where(Email.folder.ilike(folder))
    if is_read is not None:
        stmt = stmt.where(Email.is_read == is_read)
    if date_from:
        stmt = stmt.where(Email.date >= date_from)
    if date_to:
        stmt = stmt.where(Email.date <= date_to)
    if category:
        stmt = stmt.where(EmailAnalysis.category == category)
    if priority_min is not None:
        stmt = stmt.where(EmailAnalysis.priority_score >= priority_min)

    # Cursor-based pagination: order is strictly `date DESC, id DESC`
    if after:
        after_email = await session.get(Email, after)
        if after_email:
            # We want older emails than the cursor:
            # - either date is strictly smaller
            # - or date is equal, but ID is smaller (tie-breaker)
            stmt = stmt.where(
                (Email.date < after_email.date) |
                ((Email.date == after_email.date) & (Email.id < after_email.id))
            )

    # Fetch one extra to check if next page exists
    stmt = stmt.order_by(Email.date.desc(), Email.id.desc()).limit(limit + 1)
    res = await session.execute(stmt)
    rows = res.all()

    has_more = len(rows) > limit
    results = rows[:limit]

    emails_data = []
    for email, analysis in results:
        recipients = []
        try:
            if email.recipients_json:
                recipients = [Recipient(**r) for r in json.loads(email.recipients_json)]
        except Exception:
            pass

        emails_data.append(
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

    next_cursor = emails_data[-1].id if (emails_data and has_more) else None

    return {
        "emails": emails_data,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/{email_id}", response_model=EmailDetailResponse, status_code=status.HTTP_200_OK)
async def get_email_detail(
    email_id: str,
    session: AsyncSession = Depends(get_db),
) -> EmailDetailResponse:
    """Retrieve full email content (with body) and associated AI analysis."""
    email = await session.get(Email, email_id)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found",
        )
    analysis = await analysis_repo.get_by_email_id(session, email_id)
    return email_to_detail_response(email, analysis)


@router.patch("/{email_id}", response_model=EmailDetailResponse, status_code=status.HTTP_200_OK)
async def patch_email(
    email_id: str,
    request: EmailUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> EmailDetailResponse:
    """Update localized email state (read, star, labels)."""
    email = await session.get(Email, email_id)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found",
        )

    if request.is_read is not None:
        email.is_read = request.is_read
    if request.is_starred is not None:
        email.is_starred = request.is_starred
    if request.is_important is not None:
        email.is_important = request.is_important
    if request.labels is not None:
        email.labels = json.dumps(request.labels)

    await session.flush()
    await session.commit()

    analysis = await analysis_repo.get_by_email_id(session, email_id)
    return email_to_detail_response(email, analysis)


@router.post("/{email_id}/action", status_code=status.HTTP_202_ACCEPTED)
async def trigger_email_action(
    email_id: str,
    request: EmailActionRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Execute specialized folder moves (archive/trash) or mark important."""
    email = await session.get(Email, email_id)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found",
        )

    if request.action == "archive":
        email.folder = "Archive"
    elif request.action == "delete":
        email.folder = "Trash"
    elif request.action == "mark_important":
        email.is_important = True

    await session.flush()
    await session.commit()

    return {"message": f"Action '{request.action}' applied successfully to email {email_id}"}


@router.get("/{email_id}/thread", response_model=list[EmailDetailResponse], status_code=status.HTTP_200_OK)
async def get_email_thread(
    email_id: str,
    session: AsyncSession = Depends(get_db),
) -> list[EmailDetailResponse]:
    """Get all chronological messages in the conversation thread of the specified email."""
    email = await session.get(Email, email_id)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found",
        )

    if not email.thread_id:
        # Single message thread
        analysis = await analysis_repo.get_by_email_id(session, email_id)
        return [email_to_detail_response(email, analysis)]

    thread_emails = await email_repo.get_by_thread(session, email.thread_id)

    responses = []
    for te in thread_emails:
        analysis = await analysis_repo.get_by_email_id(session, te.id)
        responses.append(email_to_detail_response(te, analysis))

    return responses


async def run_async_analysis(email_id: str):
    """Background task handler for executing analysis."""
    from app.database import async_session_factory
    async with async_session_factory() as session:
        try:
            pipeline = AnalysisPipeline()
            await pipeline.analyze_email(session, email_id)
        except Exception:
            logger.exception("Failed to run background AI analysis for email %s", email_id)



@router.get("/{email_id}/summary", status_code=status.HTTP_200_OK)
async def get_or_trigger_summary(
    email_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve the summary of an email. Triggers a background AI analysis task if not analyzed."""
    email = await session.get(Email, email_id)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found",
        )

    analysis = await analysis_repo.get_by_email_id(session, email_id)
    if analysis and not analysis.is_pending and analysis.summary:
        return {"summary": analysis.summary}

    # If pending or not analyzed, trigger background processing
    background_tasks.add_task(run_async_analysis, email_id)

    # Return 202 Accepted for background processing trigger
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"detail": "AI summary analysis has been queued and is executing in the background"},
    )
