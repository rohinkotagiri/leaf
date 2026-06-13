"""Integration tests for StorageService coordinating SQL and Vector Store."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, ProviderType
from app.schemas.email import EmailMessage, Recipient, RecipientType
from app.services.storage.email_repo import EmailRepository
from app.services.storage.storage_service import StorageService
from app.services.storage.vector_store import ChromaDBStore


@pytest.fixture
def temp_vector_store(tmp_path) -> ChromaDBStore:
    persist_dir = tmp_path / "chromadb_service"
    return ChromaDBStore(persist_dir=str(persist_dir), collection_name="test_service")


@pytest.fixture
def storage_service(temp_vector_store: ChromaDBStore) -> StorageService:
    return StorageService(
        email_repo=EmailRepository(),
        vector_store=temp_vector_store,
    )


@pytest.fixture
async def test_account(db_session: AsyncSession) -> Account:
    account = Account(
        id="acct_1",
        display_name="Service Account",
        email_address="service@example.com",
        provider=ProviderType.GENERIC,
        sync_enabled=True,
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.mark.asyncio
async def test_ingest_single_email_flow(
    db_session: AsyncSession,
    storage_service: StorageService,
    test_account: Account,
) -> None:
    msg = EmailMessage(
        id="email_flow_1",
        account_id=test_account.id,
        message_id="<flow_1@example.com>",
        uid=500,
        folder="INBOX",
        subject="Integration test email",
        sender_name="System",
        sender_email="system@example.com",
        recipients=[Recipient(name="User", email="user@example.com", type=RecipientType.TO)],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Integrate SQL and ChromaDB.",
    )
    embedding = [0.1] * 384  # standard length

    # Ingest
    email_id = await storage_service.ingest_email(
        db_session,
        msg,
        embedding=embedding,
        raw_size_bytes=1000,
    )
    assert email_id == "email_flow_1"

    # Verify SQL state (is_indexed should be True)
    email = await storage_service.email_repo.get_by_id(db_session, email_id)
    assert email is not None
    assert email.is_indexed is True
    assert email.is_analyzed is False

    # Verify vector store search
    assert storage_service.vector_store is not None
    results = await storage_service.vector_store.search_similar(embedding, n_results=1)
    assert len(results) == 1
    assert results[0]["id"] == email_id


@pytest.mark.asyncio
async def test_ingest_single_email_graceful_degradation(
    db_session: AsyncSession,
    test_account: Account,
) -> None:
    # Storage service with NO vector store (or broken vector store)
    storage_service = StorageService(
        email_repo=EmailRepository(),
        vector_store=None,  # No vector store
    )

    msg = EmailMessage(
        id="email_flow_no_vector",
        account_id=test_account.id,
        message_id="<flow_no_vector@example.com>",
        uid=501,
        folder="INBOX",
        subject="No Vector Test",
        sender_name="System",
        sender_email="system@example.com",
        recipients=[],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Only save to SQL.",
    )

    # Ingest should still succeed, and is_indexed should remain False
    email_id = await storage_service.ingest_email(
        db_session,
        msg,
        embedding=[0.1] * 384,
        raw_size_bytes=500,
    )
    assert email_id == "email_flow_no_vector"

    # Verify SQL state (is_indexed is False)
    email = await storage_service.email_repo.get_by_id(db_session, email_id)
    assert email is not None
    assert email.is_indexed is False


@pytest.mark.asyncio
async def test_bulk_ingest_flow(
    db_session: AsyncSession,
    storage_service: StorageService,
    test_account: Account,
) -> None:
    msg1 = EmailMessage(
        id="email_bulk_1",
        account_id=test_account.id,
        message_id="<bulk_1@example.com>",
        uid=600,
        folder="INBOX",
        subject="First Bulk Email",
        sender_name="System",
        sender_email="system@example.com",
        recipients=[],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Bulk 1 text.",
    )
    msg2 = EmailMessage(
        id="email_bulk_2",
        account_id=test_account.id,
        message_id="<bulk_2@example.com>",
        uid=601,
        folder="INBOX",
        subject="Second Bulk Email",
        sender_name="System",
        sender_email="system@example.com",
        recipients=[],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Bulk 2 text.",
    )

    embeddings = {
        "email_bulk_1": [0.1] * 384,
        "email_bulk_2": [0.2] * 384,
    }

    # Bulk Ingest
    count = await storage_service.ingest_emails_bulk(
        db_session,
        [msg1, msg2],
        embeddings=embeddings,
    )
    assert count == 2

    # Verify SQL status
    e1 = await storage_service.email_repo.get_by_id(db_session, "email_bulk_1")
    e2 = await storage_service.email_repo.get_by_id(db_session, "email_bulk_2")
    assert e1 is not None and e1.is_indexed is True
    assert e2 is not None and e2.is_indexed is True


@pytest.mark.asyncio
async def test_delete_flow(
    db_session: AsyncSession,
    storage_service: StorageService,
    test_account: Account,
) -> None:
    msg = EmailMessage(
        id="email_delete_1",
        account_id=test_account.id,
        message_id="<delete_1@example.com>",
        uid=700,
        folder="INBOX",
        subject="Delete Me",
        sender_name="System",
        sender_email="system@example.com",
        recipients=[],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Will be deleted.",
    )

    # Ingest
    await storage_service.ingest_email(db_session, msg, embedding=[0.5] * 384)

    # Ensure added to vector store
    assert storage_service.vector_store is not None
    stats = await storage_service.vector_store.get_collection_stats()
    assert stats["count"] == 1

    # Delete
    deleted = await storage_service.delete_email(db_session, "email_delete_1")
    assert deleted is True

    # Ensure deleted from SQL
    email = await storage_service.email_repo.get_by_id(db_session, "email_delete_1")
    assert email is None

    # Ensure deleted from Vector Store
    stats = await storage_service.vector_store.get_collection_stats()
    assert stats["count"] == 0
