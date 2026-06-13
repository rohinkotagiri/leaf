"""Unit tests for ClassificationService."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, ProviderType
from app.models.email import Email
from app.models.feedback import UserFeedback
from app.services.ai.classification import ClassificationService
from app.services.ai.mock_client import MockOllamaClient


@pytest.mark.asyncio
async def test_classification_retries_invalid_json_then_returns_valid_result() -> None:
    client = MockOllamaClient(
        chat_responses=[
            "not json",
            {"category": "not-real", "priority_score": 0.1, "spam_score": 0.1, "is_phishing": False, "suggested_action": "archive", "confidence": 0.1},
            {"category": "finance", "priority_score": 0.8, "spam_score": 0.05, "is_phishing": False, "suggested_action": "review_invoice", "confidence": 0.9},
        ]
    )
    service = ClassificationService(client=client, max_invalid_json_retries=3)

    result = await service.classify_email(
        "Invoice",
        "billing@example.com",
        "Please review the invoice.",
    )

    assert result.category == "finance"
    assert result.suggested_action == "review_invoice"
    assert len(client.chat_calls) == 3
    assert all(call["format"] == "json" for call in client.chat_calls)


@pytest.mark.asyncio
async def test_classification_returns_fallback_after_invalid_json_retries() -> None:
    client = MockOllamaClient(chat_responses=["nope", "still nope", "again nope"])
    service = ClassificationService(client=client, max_invalid_json_retries=2)

    result = await service.classify_email("Hello", "alice@example.com", "Body")

    assert result.category == "other"
    assert result.suggested_action == "review_manually"
    assert result.confidence == 0.0
    assert len(client.chat_calls) == 3


@pytest.mark.asyncio
async def test_classification_uses_body_preview_and_few_shot_feedback(
    db_session: AsyncSession,
) -> None:
    account = Account(
        id="acct_ai",
        display_name="AI",
        email_address="ai@example.com",
        provider=ProviderType.GENERIC,
        sync_enabled=True,
    )
    email = Email(
        id="email_ai",
        account_id=account.id,
        message_id="<ai@example.com>",
        uid=1,
        folder="INBOX",
        subject="Bank statement",
        sender_name="Bank",
        sender_email="bank@example.com",
        body_text="Monthly statement attached.",
        date=datetime(2024, 1, 1, tzinfo=UTC),
    )
    feedback = UserFeedback(
        email_id=email.id,
        field="category",
        old_value="other",
        new_value="finance",
    )
    db_session.add(account)
    db_session.add(email)
    db_session.add(feedback)
    await db_session.flush()

    client = MockOllamaClient(
        chat_responses=[
            {"category": "work", "priority_score": 0.6, "spam_score": 0.1, "is_phishing": False, "suggested_action": "reply", "confidence": 0.8}
        ]
    )
    service = ClassificationService(client=client)
    body = ("A" * 350) + "TAIL_SHOULD_NOT_APPEAR"

    await service.classify_email("Status", "alice@example.com", body, session=db_session)

    prompt = client.chat_calls[0]["messages"][1]["content"]
    assert "Corrected category: finance" in prompt
    assert "TAIL_SHOULD_NOT_APPEAR" not in prompt
