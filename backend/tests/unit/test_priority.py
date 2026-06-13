"""Unit tests for the PriorityScorer."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.email import Email
from app.services.priority import PriorityScorer


@pytest.fixture
def mock_email() -> Email:
    """Create a mock Email model."""
    email = MagicMock(spec=Email)
    email.id = "email_test_123"
    email.account_id = "acct_123"
    email.thread_id = "thread_123"
    email.sender_name = "Alice Smith"
    email.sender_email = "alice@example.com"
    email.date = datetime.now(UTC)
    return email


@pytest.mark.asyncio
async def test_priority_scorer_base_scaling(db_session: AsyncSession, mock_email: Email) -> None:
    """Test that base AI priority from 0.0-1.0 is scaled to 0.0-10.0."""
    score = await PriorityScorer.calculate_score(
        session=db_session,
        email=mock_email,
        category="work",
        base_ai_priority=0.75,
    )
    # 0.75 * 10 = 7.5
    assert score == 7.5


@pytest.mark.asyncio
async def test_priority_scorer_contact_boost(db_session: AsyncSession, mock_email: Email) -> None:
    """Test contact boost (+2) when user has replied before."""
    # Insert account and a sent email to simulate having replied before
    account = Account(
        id=mock_email.account_id,
        display_name="User",
        email_address="user@example.com",
    )
    db_session.add(account)

    # Sent email from user to alice
    sent_email = Email(
        id="sent_123",
        account_id=account.id,
        message_id="<sent1@example.com>",
        sender_email="user@example.com",
        recipients_json='[{"name": "Alice Smith", "email": "alice@example.com", "type": "to"}]',
        subject="Re: Hello",
        body_text="Hi Alice",
        uid=1,
    )
    db_session.add(sent_email)
    await db_session.flush()

    score = await PriorityScorer.calculate_score(
        session=db_session,
        email=mock_email,
        category="work",
        base_ai_priority=0.5,
    )
    # Base: 5.0 + Boost: 2.0 = 7.0
    assert score == 7.0


@pytest.mark.asyncio
async def test_priority_scorer_deadline_boost(db_session: AsyncSession, mock_email: Email) -> None:
    """Test near-deadline boost (+3) for dates within 48 hours."""
    now = datetime.now(UTC)
    deadline_date = now + timedelta(hours=36)  # 36 hours from now (within 48h)

    extracted_dates = [
        {"date": deadline_date.isoformat(), "context": "Submit report"}
    ]

    score = await PriorityScorer.calculate_score(
        session=db_session,
        email=mock_email,
        category="work",
        base_ai_priority=0.4,
        extracted_dates=extracted_dates,
        reference_time=now,
    )
    # Base: 4.0 + Boost: 3.0 = 7.0
    assert score == 7.0


@pytest.mark.asyncio
async def test_priority_scorer_newsletter_penalty(db_session: AsyncSession, mock_email: Email) -> None:
    """Test newsletter / promo penalty (-3)."""
    # Test by category
    score_by_cat = await PriorityScorer.calculate_score(
        session=db_session,
        email=mock_email,
        category="newsletter",
        base_ai_priority=0.8,
    )
    # Base: 8.0 - Penalty: 3.0 = 5.0
    assert score_by_cat == 5.0

    # Test by sender email keyword
    mock_email.sender_email = "no-reply@newsletter.com"
    score_by_sender = await PriorityScorer.calculate_score(
        session=db_session,
        email=mock_email,
        category="updates",
        base_ai_priority=0.8,
    )
    # Base: 8.0 - Penalty: 3.0 = 5.0
    assert score_by_sender == 5.0


@pytest.mark.asyncio
async def test_priority_scorer_age_decay(db_session: AsyncSession, mock_email: Email) -> None:
    """Test age decay (-1 per day after 7 days, floor 0)."""
    now = datetime.now(UTC)
    # 10 days old email -> age_days = 10 -> age_days > 7 -> decay = 10 - 7 = 3.0
    mock_email.date = now - timedelta(days=10)

    score = await PriorityScorer.calculate_score(
        session=db_session,
        email=mock_email,
        category="work",
        base_ai_priority=0.8,
        reference_time=now,
    )
    # Base: 8.0 - Decay: 3.0 = 5.0
    assert score == 5.0
