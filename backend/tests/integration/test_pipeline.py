"""Integration tests for IngestionPipeline and AnalysisPipeline."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, ProviderType
from app.models.analysis import EmailAnalysis
from app.models.email import Email
from app.models.thread import Thread
from app.schemas.email import EmailMessage
from app.services.ai.schemas import (
    Appointment,
    ClassificationResult,
    ExtractedActionItem,
    ExtractionResult,
    NamedEntities,
)
from app.services.pipeline import AnalysisPipeline, IngestionPipeline
from app.services.storage.analysis_repo import AnalysisRepository
from app.services.storage.email_repo import EmailRepository
from app.services.storage.storage_service import StorageService
from app.services.storage.vector_store import ChromaDBStore


@pytest.fixture
def temp_vector_store(tmp_path) -> ChromaDBStore:
    persist_dir = tmp_path / "chromadb_pipeline"
    return ChromaDBStore(persist_dir=str(persist_dir), collection_name="test_pipeline")


@pytest.fixture
def storage_service(temp_vector_store: ChromaDBStore) -> StorageService:
    return StorageService(
        email_repo=EmailRepository(),
        vector_store=temp_vector_store,
    )


@pytest.fixture
async def test_account(db_session: AsyncSession) -> Account:
    account = Account(
        id="acct_pipeline_test",
        display_name="Pipeline Tester",
        email_address="pipeline@example.com",
        provider=ProviderType.GENERIC,
        sync_enabled=True,
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.mark.asyncio
@patch("app.services.ai.embedding.EmbeddingService.embed_text", new_callable=AsyncMock)
async def test_ingestion_pipeline_success(
    mock_embed,
    db_session: AsyncSession,
    storage_service: StorageService,
    test_account: Account,
) -> None:
    """Test standard ingestion flow: DB save, vector store embed, and analysis queueing."""
    mock_embed.return_value = [0.15] * 384

    pipeline = IngestionPipeline(
        storage_service=storage_service,
        embedding_service=patch("app.services.ai.embedding.EmbeddingService").start()(),
        analysis_repo=AnalysisRepository(),
    )
    pipeline.embedding_service.embed_text = mock_embed
    pipeline.embedding_service.model = "mock-embed-text"

    msg = EmailMessage(
        id="msg_ingest_1",
        account_id=test_account.id,
        message_id="<ingest1@example.com>",
        uid=101,
        folder="INBOX",
        subject="Ingestion Pipeline Test",
        sender_name="Ingester",
        sender_email="ingest@example.com",
        recipients=[],
        date=datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC),
        body_text="Body content for vector database.",
    )

    result = await pipeline.ingest_email(db_session, msg)
    await db_session.commit()

    assert "deduplication" in result.stages_completed
    assert "sql_save" in result.stages_completed
    assert "embedding" in result.stages_completed
    assert "enqueue" in result.stages_completed
    assert not result.errors

    # Verify SQL record is saved
    email = await storage_service.email_repo.get_by_id(db_session, "msg_ingest_1")
    assert email is not None
    assert email.is_indexed is True
    assert email.is_analyzed is False

    # Verify pending analysis record created
    analysis = await AnalysisRepository().get_by_email_id(db_session, "msg_ingest_1")
    assert analysis is not None
    assert analysis.is_pending is True

    # Check deduplication on second run
    dedup_result = await pipeline.ingest_email(db_session, msg)
    assert dedup_result.stages_completed == ["deduplication"]
    assert not dedup_result.errors


@pytest.mark.asyncio
@patch("app.services.ai.classification.ClassificationService.classify_email", new_callable=AsyncMock)
@patch("app.services.ai.summarization.SummarizationService.summarize_email", new_callable=AsyncMock)
@patch("app.services.ai.extraction.ExtractionService.extract_email", new_callable=AsyncMock)
@patch("app.services.websocket.manager.broadcast", new_callable=AsyncMock)
async def test_analysis_pipeline_spam_gate(
    mock_ws_broadcast,
    mock_extract,
    mock_summarize,
    mock_classify,
    db_session: AsyncSession,
    test_account: Account,
) -> None:
    """Test spam gating: if classification spam score > 0.85, deep analysis is skipped."""
    # Seed thread and email
    thread = Thread(id="thread_spam", account_id=test_account.id, subject_base="Spam Thread")
    db_session.add(thread)
    email = Email(
        id="msg_spam_1",
        account_id=test_account.id,
        thread_id=thread.id,
        message_id="<spam1@example.com>",
        subject="Buy Viagra Now!",
        sender_name="Spammer",
        sender_email="spam@viagra.com",
        recipients_json="[]",
        date=datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC),
        body_text="Viagra deals",
        uid=102,
    )
    db_session.add(email)

    # Analysis record (pending)
    analysis = EmailAnalysis(email_id="msg_spam_1", is_pending=True)
    db_session.add(analysis)
    await db_session.flush()

    mock_classify.return_value = ClassificationResult(
        category="spam",
        priority_score=0.0,
        spam_score=0.99,
        is_phishing=False,
        suggested_action="archive",
        confidence=0.98,
    )

    pipeline = AnalysisPipeline(
        email_repo=EmailRepository(),
        analysis_repo=AnalysisRepository(),
        classification_service=patch("app.services.ai.classification.ClassificationService").start()(),
        summarization_service=patch("app.services.ai.summarization.SummarizationService").start()(),
        extraction_service=patch("app.services.ai.extraction.ExtractionService").start()(),
    )
    pipeline.classification_service.classify_email = mock_classify
    pipeline.classification_service.model = "mock-fast-model"

    result = await pipeline.analyze_email(db_session, "msg_spam_1")
    await db_session.commit()

    assert result.success
    assert "classification" in result.stages_completed
    assert "spam_gate" in result.stages_completed
    # Summarize and extract should not run
    assert "summarization" not in result.stages_completed
    assert "extraction" not in result.stages_completed
    assert result.is_spam is True

    # Verify DB state
    db_analysis = await AnalysisRepository().get_by_email_id(db_session, "msg_spam_1")
    assert db_analysis.is_pending is False
    assert db_analysis.category == "spam"
    assert db_analysis.summary == "Spam filtered (fast pass)"

    # Verify WebSocket notification was broadcasted
    mock_ws_broadcast.assert_called_once_with({"type": "analysis_complete", "email_id": "msg_spam_1"})


@pytest.mark.asyncio
@patch("app.services.ai.classification.ClassificationService.classify_email", new_callable=AsyncMock)
@patch("app.services.ai.summarization.SummarizationService.summarize_email", new_callable=AsyncMock)
@patch("app.services.ai.summarization.SummarizationService.summarize_thread", new_callable=AsyncMock)
@patch("app.services.ai.extraction.ExtractionService.extract_email", new_callable=AsyncMock)
@patch("app.services.websocket.manager.broadcast", new_callable=AsyncMock)
async def test_analysis_pipeline_deep_pass_and_thread_summary(
    mock_ws_broadcast,
    mock_extract,
    mock_summarize_thread,
    mock_summarize_email,
    mock_classify,
    db_session: AsyncSession,
    test_account: Account,
) -> None:
    """Test full analysis pass: class, summarize, extract fact and trigger thread summary on last message."""
    # Seed thread and 2 emails
    thread = Thread(id="thread_clean", account_id=test_account.id, subject_base="Clean Thread")
    db_session.add(thread)

    e1 = Email(
        id="msg_clean_1",
        account_id=test_account.id,
        thread_id=thread.id,
        message_id="<clean1@example.com>",
        subject="Important project updates",
        sender_name="Bob",
        sender_email="bob@example.com",
        recipients_json="[]",
        date=datetime(2026, 6, 13, 10, 0, 0, tzinfo=UTC),
        body_text="Bob's updates",
        uid=103,
        is_analyzed=True,  # already analyzed
    )
    e2 = Email(
        id="msg_clean_2",
        account_id=test_account.id,
        thread_id=thread.id,
        message_id="<clean2@example.com>",
        subject="Re: Important project updates",
        sender_name="Alice",
        sender_email="alice@example.com",
        recipients_json="[]",
        date=datetime(2026, 6, 13, 11, 0, 0, tzinfo=UTC),
        body_text="Alice's response with deadline 15-Jun-2026",
        uid=104,
        is_analyzed=False,
    )
    db_session.add(e1)
    db_session.add(e2)

    a1 = EmailAnalysis(email_id="msg_clean_1", is_pending=False, category="work")
    a2 = EmailAnalysis(email_id="msg_clean_2", is_pending=True)
    db_session.add(a1)
    db_session.add(a2)
    await db_session.flush()

    mock_classify.return_value = ClassificationResult(
        category="work",
        priority_score=0.7,
        spam_score=0.05,
        is_phishing=False,
        suggested_action="reply",
        confidence=0.9,
    )

    mock_summarize_email.return_value = "Detailed summary of Alice's updates."

    mock_extract.return_value = ExtractionResult(
        action_items=[
            ExtractedActionItem(task="Review proposal", deadline="2026-06-15T12:00:00Z", priority="high")
        ],
        appointments=[
            Appointment(title="Sync Meeting", date="2026-06-15T15:00:00Z")
        ],
        commitments=[],
        entities=NamedEntities(people=["Alice", "Bob"]),
        confidence=0.95,
    )

    mock_summarize_thread.return_value = "Bob gave updates. Alice replied requesting a review."

    pipeline = AnalysisPipeline(
        email_repo=EmailRepository(),
        analysis_repo=AnalysisRepository(),
        classification_service=patch("app.services.ai.classification.ClassificationService").start()(),
        summarization_service=patch("app.services.ai.summarization.SummarizationService").start()(),
        extraction_service=patch("app.services.ai.extraction.ExtractionService").start()(),
    )
    pipeline.classification_service.classify_email = mock_classify
    pipeline.summarization_service.summarize_email = mock_summarize_email
    pipeline.summarization_service.summarize_thread = mock_summarize_thread
    pipeline.summarization_service.model = "mock-deep-model"
    pipeline.extraction_service.extract_email = mock_extract

    # Run analysis on message 2
    result = await pipeline.analyze_email(db_session, "msg_clean_2")
    await db_session.commit()

    assert result.success
    assert "classification" in result.stages_completed
    assert "summarization" in result.stages_completed
    assert "extraction" in result.stages_completed
    assert "priority_score" in result.stages_completed
    assert "save" in result.stages_completed
    assert "thread_summary" in result.stages_completed  # Since e1 and e2 are both analyzed now
    assert "websocket_emit" in result.stages_completed

    # Check DB state
    db_analysis = await AnalysisRepository().get_by_email_id(db_session, "msg_clean_2")
    # pyrefly: ignore [missing-attribute]
    assert db_analysis.is_pending is False
    assert db_analysis.category == "work"
    assert db_analysis.summary == "Detailed summary of Alice's updates."
    assert "Review proposal" in db_analysis.action_items
    assert "Sync Meeting" in db_analysis.extracted_dates

    # Check Thread summary update
    db_thread = await db_session.get(Thread, thread.id)
    assert db_thread.summary == "Bob gave updates. Alice replied requesting a review."
