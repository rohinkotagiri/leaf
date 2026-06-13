"""Unit tests for EmailRepository using in-memory SQLite."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, ProviderType
from app.schemas.email import Attachment, EmailMessage, Recipient, RecipientType
from app.services.storage.email_repo import EmailRepository


@pytest.fixture
def email_repo() -> EmailRepository:
    return EmailRepository()


@pytest.fixture
async def test_account(db_session: AsyncSession) -> Account:
    account = Account(
        id="acct_1",
        display_name="Test Account",
        email_address="test@example.com",
        provider=ProviderType.GENERIC,
        sync_enabled=True,
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.mark.asyncio
async def test_save_and_get_email(
    db_session: AsyncSession,
    email_repo: EmailRepository,
    test_account: Account,
) -> None:
    msg = EmailMessage(
        id="email_1",
        account_id=test_account.id,
        message_id="<msg_1@example.com>",
        uid=101,
        folder="INBOX",
        subject="Hello World",
        sender_name="Alice",
        sender_email="alice@example.com",
        recipients=[
            Recipient(name="Bob", email="bob@example.com", type=RecipientType.TO)
        ],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Hello Bob, this is raw text.",
        body_html="<html><body><p>Hello Bob, this is raw text.</p></body></html>",
        attachments=[Attachment(filename="doc.pdf", content_type="application/pdf", size=1024)],
        flags=["\\Seen"],
    )

    # Save
    email = await email_repo.save_email(db_session, msg, raw_size_bytes=5000)
    assert email.id == "email_1"
    assert email.subject == "Hello World"
    assert email.is_read is True
    assert email.is_starred is False

    # Get by ID
    retrieved = await email_repo.get_by_id(db_session, "email_1")
    assert retrieved is not None
    assert retrieved.subject == "Hello World"
    assert retrieved.sender_name == "Alice"
    assert retrieved.has_attachments is True

    # Convert to message DTO
    dto = email_repo.email_to_message(retrieved)
    assert dto.id == msg.id
    assert dto.subject == msg.subject
    assert dto.sender_email == msg.sender_email
    assert len(dto.recipients) == 1
    assert dto.recipients[0].name == "Bob"
    assert len(dto.attachments) == 1
    assert dto.attachments[0].filename == "doc.pdf"


@pytest.mark.asyncio
async def test_save_emails_bulk(
    db_session: AsyncSession,
    email_repo: EmailRepository,
    test_account: Account,
) -> None:
    msg1 = EmailMessage(
        id="email_1",
        account_id=test_account.id,
        message_id="<msg_1@example.com>",
        uid=101,
        folder="INBOX",
        subject="First Email",
        sender_name="Alice",
        sender_email="alice@example.com",
        recipients=[],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Body 1",
    )
    msg2 = EmailMessage(
        id="email_2",
        account_id=test_account.id,
        message_id="<msg_2@example.com>",
        uid=102,
        folder="INBOX",
        subject="Second Email",
        sender_name="Charlie",
        sender_email="charlie@example.com",
        recipients=[],
        date=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
        body_text="Body 2",
    )

    # Bulk save
    inserted = await email_repo.save_emails_bulk(db_session, [msg1, msg2])
    # SQLite returns rowcount = number of inserted rows
    assert inserted == 2

    # Verify counts
    count = await email_repo.count_by_account(db_session, test_account.id)
    assert count == 2

    # Save again (should do nothing because of ON CONFLICT DO NOTHING)
    inserted_again = await email_repo.save_emails_bulk(db_session, [msg1, msg2])
    assert inserted_again == 0


@pytest.mark.asyncio
async def test_get_paginated_and_filters(
    db_session: AsyncSession,
    email_repo: EmailRepository,
    test_account: Account,
) -> None:
    msg1 = EmailMessage(
        id="email_1",
        account_id=test_account.id,
        message_id="<msg_1@example.com>",
        uid=101,
        folder="INBOX",
        subject="First Email",
        sender_name="Alice",
        sender_email="alice@example.com",
        recipients=[],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Body 1",
        flags=["\\Seen"],
    )
    msg2 = EmailMessage(
        id="email_2",
        account_id=test_account.id,
        message_id="<msg_2@example.com>",
        uid=102,
        folder="Sent",
        subject="Second Email",
        sender_name="Charlie",
        sender_email="charlie@example.com",
        recipients=[],
        date=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
        body_text="Body 2",
        flags=[],
    )

    await email_repo.save_email(db_session, msg1)
    await email_repo.save_email(db_session, msg2)

    # Test pagination (order_by date desc)
    emails, total = await email_repo.get_paginated(db_session, account_id=test_account.id, limit=1)
    assert total == 2
    assert len(emails) == 1
    assert emails[0].id == "email_2"  # second email is newer

    # Test folder filter
    emails, total = await email_repo.get_paginated(db_session, folder="Sent")
    assert total == 1
    assert emails[0].id == "email_2"

    # Test is_read filter
    emails, total = await email_repo.get_paginated(db_session, is_read=True)
    assert total == 1
    assert emails[0].id == "email_1"


@pytest.mark.asyncio
async def test_search_and_updates(
    db_session: AsyncSession,
    email_repo: EmailRepository,
    test_account: Account,
) -> None:
    msg = EmailMessage(
        id="email_1",
        account_id=test_account.id,
        message_id="<msg_1@example.com>",
        uid=101,
        folder="INBOX",
        subject="First Email",
        sender_name="Alice",
        sender_email="alice@example.com",
        recipients=[],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Body 1",
    )
    await email_repo.save_email(db_session, msg)

    # Search by metadata
    results = await email_repo.search_by_metadata(
        db_session,
        account_id=test_account.id,
        subject_contains="First",
        date_from=datetime(2023, 1, 1, tzinfo=UTC),
    )
    assert len(results) == 1
    assert results[0].id == "email_1"

    # Update mark read/unread
    await email_repo.mark_read(db_session, "email_1", is_read=True)
    email = await email_repo.get_by_id(db_session, "email_1")
    assert email is not None
    assert email.is_read is True

    # Update labels
    await email_repo.update_labels(db_session, "email_1", ["inbox", "work"])
    email = await email_repo.get_by_id(db_session, "email_1")
    assert email is not None
    assert "work" in email.labels

    # Mark indexed / analyzed
    await email_repo.mark_indexed(db_session, "email_1")
    await email_repo.mark_analyzed(db_session, "email_1")
    email = await email_repo.get_by_id(db_session, "email_1")
    assert email is not None
    assert email.is_indexed is True
    assert email.is_analyzed is True


@pytest.mark.asyncio
async def test_email_repo_edge_cases(
    db_session: AsyncSession,
    email_repo: EmailRepository,
    test_account: Account,
) -> None:
    # 1. Bulk save with empty list
    assert await email_repo.save_emails_bulk(db_session, []) == 0

    # 2. Get unanalyzed and get_unindexed
    msg = EmailMessage(
        id="email_edge",
        account_id=test_account.id,
        message_id="<edge@example.com>",
        uid=200,
        folder="INBOX",
        subject="Edge cases",
        sender_name="Alice",
        sender_email="alice@example.com",
        recipients=[],
        date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        body_text="Edge",
    )
    await email_repo.save_email(db_session, msg)

    unanalyzed = await email_repo.get_unanalyzed(db_session)
    assert any(e.id == "email_edge" for e in unanalyzed)

    unindexed = await email_repo.get_unindexed(db_session)
    assert any(e.id == "email_edge" for e in unindexed)

    # 3. Get by thread
    # Assign thread id
    email_obj = await email_repo.get_by_id(db_session, "email_edge")
    assert email_obj is not None
    email_obj.thread_id = "thread_xyz"
    await db_session.flush()

    by_thread = await email_repo.get_by_thread(db_session, "thread_xyz")
    assert len(by_thread) == 1
    assert by_thread[0].id == "email_edge"

    # 4. Search by metadata filters: date_to, sender, folder, has_attachments
    results = await email_repo.search_by_metadata(
        db_session,
        sender="alice",
        date_to=datetime(2025, 1, 1, tzinfo=UTC),
        folder="INBOX",
        has_attachments=False,
    )
    assert len(results) == 1
    assert results[0].id == "email_edge"

