"""Unit tests for AnalysisRepository using in-memory SQLite."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, ProviderType
from app.models.email import Email
from app.schemas.analysis import ActionItem, AnalysisCreate, ExtractedDate
from app.services.storage.analysis_repo import AnalysisRepository


@pytest.fixture
def analysis_repo() -> AnalysisRepository:
    return AnalysisRepository()


@pytest.fixture
async def test_email(db_session: AsyncSession) -> Email:
    account = Account(
        id="acct_1",
        display_name="Test Account",
        email_address="test@example.com",
        provider=ProviderType.GENERIC,
        sync_enabled=True,
    )
    db_session.add(account)
    await db_session.flush()

    email = Email(
        id="email_1",
        account_id=account.id,
        message_id="<msg_1@example.com>",
        uid=101,
        folder="INBOX",
        subject="Action Required",
        sender_name="Alice",
        sender_email="alice@example.com",
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    db_session.add(email)
    await db_session.flush()
    return email


@pytest.mark.asyncio
async def test_save_and_get_analysis(
    db_session: AsyncSession,
    analysis_repo: AnalysisRepository,
    test_email: Email,
) -> None:
    data = AnalysisCreate(
        email_id=test_email.id,
        category="work",
        priority_score=0.85,
        spam_score=0.05,
        is_phishing=False,
        summary="Need to update reports by Friday.",
        action_items=[
            ActionItem(task="Update quarterly report", deadline="Friday", priority="high")
        ],
        extracted_dates=[
            ExtractedDate(date="Friday", context="report deadline")
        ],
        extracted_entities={"organizations": ["Acme Corp"]},
        suggested_action="Reply with attachment",
        sentiment="neutral",
        model_name="llama3",
        prompt_version="v1.0",
        confidence=0.9,
    )

    # Save analysis
    analysis = await analysis_repo.save_analysis(db_session, data)
    assert analysis.email_id == test_email.id
    assert analysis.category == "work"
    assert analysis.priority_score == 0.85

    # Retrieve
    retrieved = await analysis_repo.get_by_email_id(db_session, test_email.id)
    assert retrieved is not None
    assert retrieved.summary == "Need to update reports by Friday."
    assert "quarterly report" in retrieved.action_items

    # Update partial
    await analysis_repo.update_analysis(db_session, test_email.id, priority_score=0.95, category="urgent")
    retrieved = await analysis_repo.get_by_email_id(db_session, test_email.id)
    assert retrieved is not None
    assert retrieved.priority_score == 0.95
    assert retrieved.category == "urgent"

    # Save existing again (triggers the existing update flow)
    data.category = "updates"
    updated_analysis = await analysis_repo.save_analysis(db_session, data)
    assert updated_analysis.category == "updates"

    # Update analysis with pre-serialized JSON string fields to hit serialization skip branch
    await analysis_repo.update_analysis(
        db_session,
        test_email.id,
        action_items="[]",
        extracted_dates="[]",
        extracted_entities="{}",
    )


@pytest.mark.asyncio
async def test_get_unanalyzed_email_ids(
    db_session: AsyncSession,
    analysis_repo: AnalysisRepository,
    test_email: Email,
) -> None:
    # Initially the email has no analysis, but it's not marked analyzed
    ids = await analysis_repo.get_unanalyzed_email_ids(db_session)
    assert test_email.id in ids

    # Save analysis
    data = AnalysisCreate(
        email_id=test_email.id,
        category="work",
        priority_score=0.8,
    )
    await analysis_repo.save_analysis(db_session, data)

    # Now mark the email analyzed (simulating storage service flow)
    test_email.is_analyzed = True
    await db_session.flush()

    # Should no longer be unanalyzed
    ids = await analysis_repo.get_unanalyzed_email_ids(db_session)
    assert test_email.id not in ids
