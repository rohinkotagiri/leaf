"""Unit tests for summarization, extraction, and spam services."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.email import EmailMessage
from app.services.ai.extraction import ExtractionService
from app.services.ai.mock_client import MockOllamaClient
from app.services.ai.spam import SpamDetectionService
from app.services.ai.summarization import SummarizationService


@pytest.mark.asyncio
async def test_summarize_thread_orders_messages_chronologically() -> None:
    client = MockOllamaClient(chat_responses=["Thread summary."])
    service = SummarizationService(client=client)
    later = EmailMessage(
        subject="Later",
        sender_email="later@example.com",
        body_text="Second message",
        date=datetime(2024, 1, 2, tzinfo=UTC),
    )
    earlier = EmailMessage(
        subject="Earlier",
        sender_email="earlier@example.com",
        body_text="First message",
        date=datetime(2024, 1, 1, tzinfo=UTC),
    )

    summary = await service.summarize_thread([later, earlier])

    prompt = client.chat_calls[0]["messages"][1]["content"]
    assert summary == "Thread summary."
    assert prompt.index("Subject: Earlier") < prompt.index("Subject: Later")


@pytest.mark.asyncio
async def test_extract_key_points_returns_json_points() -> None:
    client = MockOllamaClient()
    service = SummarizationService(client=client)

    points = await service.extract_key_points(
        "Project",
        "alice@example.com",
        "We need a project update by Friday.",
    )

    assert points == ["Project update requested", "Deadline is Friday"]


@pytest.mark.asyncio
async def test_extraction_returns_structured_result_and_fallback() -> None:
    service = ExtractionService(client=MockOllamaClient())

    result = await service.extract_email(
        "Report",
        "alice@example.com",
        "Please send the report by Friday. Alice from Acme Corp will review it.",
    )

    assert result.action_items[0].task == "Send the report"
    assert result.entities.organizations == ["Acme Corp"]

    fallback = await ExtractionService(
        client=MockOllamaClient(chat_responses=["not json"])
    ).extract_email("Bad", "sender@example.com", "Body")
    assert fallback.action_items == []
    assert fallback.confidence == 0.0


@pytest.mark.asyncio
async def test_spam_detection_combines_url_header_and_llm_signals() -> None:
    client = MockOllamaClient(
        chat_responses=[
            {
                "spam_score": 0.9,
                "is_phishing": True,
                "reasons": ["Credential theft language"],
                "confidence": 0.9,
            }
        ]
    )
    service = SpamDetectionService(client=client)

    result = await service.analyze_email(
        "Urgent account update",
        "security@example.com",
        "Verify now: http://192.168.0.1/login",
        raw_headers={"Authentication-Results": "spf=fail dkim=fail dmarc=fail"},
    )

    assert result.is_spam is True
    assert result.is_phishing is True
    assert result.combined_score > 0.75
    assert result.urls[0].domain == "192.168.0.1"
    assert "spf_failed" in result.header_signal.reasons


@pytest.mark.asyncio
async def test_spam_detection_uses_heuristic_score_when_llm_fails() -> None:
    service = SpamDetectionService(client=MockOllamaClient(chat_responses=["not json"]))

    result = await service.analyze_email(
        "Verify",
        "sender@example.com",
        "Click http://bit.ly/verify-login",
        raw_headers=None,
    )

    assert result.llm_signal is None
    assert result.confidence == 0.45
    assert result.url_score > 0
    assert result.header_score > 0
