"""Priority Scorer service for calculating final email priority scores."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email import Email
from app.models.account import Account

logger = logging.getLogger(__name__)

# Pattern to identify typical newsletter / automated senders
NEWSLETTER_SENDER_PATTERN = re.compile(
    r"(newsletter|promo|marketing|info|bounce|no-reply|noreply|alerts|notification)",
    re.IGNORECASE
)


class PriorityScorer:
    """Calculates final priority score for an email based on AI classification and business rules."""

    @staticmethod
    async def calculate_score(
        session: AsyncSession,
        email: Email,
        category: str,
        base_ai_priority: float,  # 0.0 to 1.0
        extracted_dates: list[dict] | None = None,
        reference_time: datetime | None = None,
    ) -> float:
        """Calculate the final priority score from 0.0 to 10.0.

        Rules:
        - Base: AI priority score (0-10, scaled from 0.0-1.0)
        - Boost: sender is in contacts, has replied before (+2)
        - Boost: detected deadline within 48 hours (+3)
        - Penalty: newsletter/promotional sender (-3)
        - Decay: emails older than 7 days without action (-1 per day, floor 0)
        """
        # Base AI priority (0 to 10)
        score = base_ai_priority * 10.0
        logger.debug("Base AI priority score for email %s: %.2f", email.id[:12], score)

        # Reference time for deadline/decay calculations
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        # 1. Boost: sender is in contacts or has replied before (+2)
        has_replied = False
        try:
            account = await session.get(Account, email.account_id)
            user_email = account.email_address if account else ""

            if user_email:
                # Check 1: Did user ever send an email to this sender?
                stmt = (
                    select(func.count(Email.id))
                    .where(Email.account_id == email.account_id)
                    .where(Email.sender_email == user_email)
                    .where(Email.recipients_json.like(f"%{email.sender_email}%"))
                )
                res = await session.execute(stmt)
                if (res.scalar() or 0) > 0:
                    has_replied = True

                # Check 2: Did user participate in the same thread?
                if not has_replied and email.thread_id:
                    stmt_thread = (
                        select(func.count(Email.id))
                        .where(Email.thread_id == email.thread_id)
                        .where(Email.sender_email == user_email)
                    )
                    res_thread = await session.execute(stmt_thread)
                    if (res_thread.scalar() or 0) > 0:
                        has_replied = True
        except Exception:
            logger.exception("Failed to check sender reply status for email %s", email.id[:12])

        if has_replied:
            score += 2.0
            logger.debug("Applied contact/replied boost (+2) for email %s", email.id[:12])

        # 2. Boost: detected deadline within 48 hours (+3)
        has_near_deadline = False
        if extracted_dates:
            for date_item in extracted_dates:
                date_str = date_item.get("date")
                if not date_str:
                    continue
                try:
                    # Parse ISO format or fallback
                    deadline_dt = datetime.fromisoformat(date_str)
                    if deadline_dt.tzinfo is None:
                        deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)

                    # Check if the deadline is within the next 48 hours (172800 seconds)
                    diff_seconds = (deadline_dt - ref_time).total_seconds()
                    if 0 <= diff_seconds <= 172800:
                        has_near_deadline = True
                        break
                except Exception:
                    pass

        if has_near_deadline:
            score += 3.0
            logger.debug("Applied near-deadline boost (+3) for email %s", email.id[:12])

        # 3. Penalty: newsletter / promotional sender (-3)
        is_newsletter_or_promo = (
            category.lower().strip() in ("newsletter", "shopping") or
            bool(NEWSLETTER_SENDER_PATTERN.search(email.sender_email)) or
            bool(NEWSLETTER_SENDER_PATTERN.search(email.sender_name))
        )
        if is_newsletter_or_promo:
            score -= 3.0
            logger.debug("Applied newsletter/promo penalty (-3) for email %s", email.id[:12])

        # Clamp score between 0.0 and 10.0 before decay
        score = max(0.0, min(10.0, score))

        # 4. Decay: emails older than 7 days without action (-1 per day, floor 0)
        email_date = email.date
        if email_date:
            if email_date.tzinfo is None:
                email_date = email_date.replace(tzinfo=timezone.utc)

            age_seconds = (ref_time - email_date).total_seconds()
            age_days = int(age_seconds / 86400)
            if age_days > 7:
                decay = float(age_days - 7)
                score = max(0.0, score - decay)
                logger.debug("Applied age decay (-%.1f) for email %s (age: %d days)", decay, email.id[:12], age_days)

        final_score = round(max(0.0, min(10.0, score)), 2)
        logger.info("Final priority score for email %s: %.2f", email.id[:12], final_score)
        return final_score
