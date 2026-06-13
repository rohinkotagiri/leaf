"""Router for tracking and reporting user feedback corrections on AI processing."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.analysis import EmailAnalysis
from app.models.feedback import UserFeedback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackCreateRequest(BaseModel):
    """Payload to log a correction feedback item."""
    email_id: str
    field: str
    old_value: str | None = None
    new_value: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    request: FeedbackCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit a correction to an AI-analyzed field, saving it to database and updating the analysis."""
    # 1. Verify email analysis exists
    analysis = await session.get(EmailAnalysis, request.email_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No AI analysis found for email_id {request.email_id}",
        )

    # 2. Update the actual analysis database record with the new corrected value
    try:
        if request.field == "category":
            analysis.category = request.new_value
        elif request.field == "priority_score":
            analysis.priority_score = float(request.new_value)
        elif request.field == "spam_score":
            analysis.spam_score = float(request.new_value)
            if float(request.new_value) > 0.85:
                analysis.category = "spam"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field '{request.field}' is not corrected or modifiable via feedback",
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid value type for field '{request.field}': '{request.new_value}'",
        ) from e

    # 3. Save User Feedback history record
    feedback = UserFeedback(
        email_id=request.email_id,
        field=request.field,
        old_value=request.old_value,
        new_value=request.new_value,
    )
    session.add(feedback)

    await session.flush()
    await session.commit()

    return {"message": "Feedback submitted and AI analysis updated successfully"}


@router.get("/stats", status_code=status.HTTP_200_OK)
async def get_feedback_stats(
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get correction statistics grouped by field name."""
    stmt = (
        select(UserFeedback.field, func.count(UserFeedback.id))
        .group_by(UserFeedback.field)
    )
    res = await session.execute(stmt)

    stats = {}
    for field, count in res.all():
        stats[field] = count

    return {
        "total_corrections": sum(stats.values()),
        "by_field": stats,
    }
