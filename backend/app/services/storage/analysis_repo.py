"""Analysis repository — async CRUD for AI email analysis results."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import EmailAnalysis
from app.models.email import Email
from app.schemas.analysis import AnalysisCreate

logger = logging.getLogger(__name__)


class AnalysisRepository:
    """Async repository for EmailAnalysis CRUD operations."""

    async def save_analysis(
        self,
        session: AsyncSession,
        data: AnalysisCreate,
    ) -> EmailAnalysis:
        """Save a new analysis result. Upserts if one already exists for the email."""
        existing = await self.get_by_email_id(session, data.email_id)

        if existing is not None:
            # Update existing
            existing.is_pending = data.is_pending
            existing.category = data.category
            existing.priority_score = data.priority_score
            existing.spam_score = data.spam_score
            existing.is_phishing = data.is_phishing
            existing.summary = data.summary
            existing.action_items = json.dumps(
                [item.model_dump() for item in data.action_items]
            )
            existing.extracted_dates = json.dumps(
                [d.model_dump() for d in data.extracted_dates]
            )
            existing.extracted_entities = json.dumps(data.extracted_entities)
            existing.suggested_action = data.suggested_action
            existing.sentiment = data.sentiment
            existing.model_name = data.model_name
            existing.prompt_version = data.prompt_version
            existing.confidence = data.confidence
            await session.flush()
            logger.debug("Updated analysis for email %s", data.email_id[:12])
            return existing

        analysis = EmailAnalysis(
            email_id=data.email_id,
            is_pending=data.is_pending,
            category=data.category,
            priority_score=data.priority_score,
            spam_score=data.spam_score,
            is_phishing=data.is_phishing,
            summary=data.summary,
            action_items=json.dumps(
                [item.model_dump() for item in data.action_items]
            ),
            extracted_dates=json.dumps(
                [d.model_dump() for d in data.extracted_dates]
            ),
            extracted_entities=json.dumps(data.extracted_entities),
            suggested_action=data.suggested_action,
            sentiment=data.sentiment,
            model_name=data.model_name,
            prompt_version=data.prompt_version,
            confidence=data.confidence,
        )
        session.add(analysis)
        await session.flush()

        logger.debug("Saved analysis for email %s", data.email_id[:12])
        return analysis

    async def get_by_email_id(
        self, session: AsyncSession, email_id: str
    ) -> EmailAnalysis | None:
        """Get analysis for a specific email."""
        return await session.get(EmailAnalysis, email_id)

    async def get_unanalyzed_email_ids(
        self, session: AsyncSession, limit: int = 50
    ) -> list[str]:
        """Get IDs of emails that don't have analysis results.

        Returns email IDs that exist in the emails table but not in
        email_analyses (left anti-join).
        """
        stmt = (
            select(Email.id)
            .outerjoin(EmailAnalysis, Email.id == EmailAnalysis.email_id)
            .where(EmailAnalysis.email_id.is_(None))
            .where(Email.is_analyzed == False)  # noqa: E712
            .order_by(Email.date.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_analysis(
        self,
        session: AsyncSession,
        email_id: str,
        **updates: object,
    ) -> None:
        """Update specific fields of an analysis.

        Args:
            session: Database session.
            email_id: The email ID whose analysis to update.
            **updates: Field name → new value pairs.
        """
        analysis = await session.get(EmailAnalysis, email_id)
        if analysis and updates:
            json_fields = {"action_items", "extracted_dates", "extracted_entities"}
            for key, value in updates.items():
                if key in json_fields and not isinstance(value, str):
                    setattr(analysis, key, json.dumps(value))
                else:
                    setattr(analysis, key, value)
            await session.flush()
            logger.debug("Updated analysis fields %s for email %s", list(updates.keys()), email_id[:12])
