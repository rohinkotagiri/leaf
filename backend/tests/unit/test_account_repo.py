"""Unit tests for AccountRepository using in-memory SQLite."""

from datetime import datetime, UTC
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import ProviderType
from app.schemas.account import AccountCreate
from app.services.storage.account_repo import AccountRepository


@pytest.fixture
def account_repo() -> AccountRepository:
    return AccountRepository()


@pytest.mark.asyncio
async def test_create_and_retrieve_account(
    db_session: AsyncSession,
    account_repo: AccountRepository,
) -> None:
    data = AccountCreate(
        email_address="alice@example.com",
        display_name="Alice Smith",
        provider=ProviderType.GENERIC,
        imap_host="imap.example.com",
        imap_port=993,
        use_ssl=True,
        credentials_key="key_123",
    )

    account = await account_repo.create(db_session, data)
    assert account.id is not None
    assert account.email_address == "alice@example.com"
    assert account.sync_enabled is True

    # Retrieve by ID
    retrieved = await account_repo.get_by_id(db_session, account.id)
    assert retrieved is not None
    assert retrieved.display_name == "Alice Smith"

    # Retrieve by Email
    retrieved_email = await account_repo.get_by_email(db_session, "alice@example.com")
    assert retrieved_email is not None
    assert retrieved_email.id == account.id


@pytest.mark.asyncio
async def test_update_and_sync_status(
    db_session: AsyncSession,
    account_repo: AccountRepository,
) -> None:
    data = AccountCreate(
        email_address="bob@example.com",
        display_name="Bob Jones",
    )
    account = await account_repo.create(db_session, data)

    # Partial update
    await account_repo.update(db_session, account.id, display_name="Robert", sync_enabled=False)
    retrieved = await account_repo.get_by_id(db_session, account.id)
    assert retrieved is not None
    assert retrieved.display_name == "Robert"
    assert retrieved.sync_enabled is False

    # Update sync status
    sync_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    await account_repo.update_sync_status(db_session, account.id, sync_time, "cursor_xyz")
    retrieved = await account_repo.get_by_id(db_session, account.id)
    assert retrieved is not None
    assert retrieved.last_sync_at == sync_time
    assert retrieved.sync_cursor == "cursor_xyz"


@pytest.mark.asyncio
async def test_get_all_active_and_delete(
    db_session: AsyncSession,
    account_repo: AccountRepository,
) -> None:
    data1 = AccountCreate(email_address="user1@example.com")
    data2 = AccountCreate(email_address="user2@example.com")

    acct1 = await account_repo.create(db_session, data1)
    acct2 = await account_repo.create(db_session, data2)

    # Disable sync for account 2
    await account_repo.update(db_session, acct2.id, sync_enabled=False)

    # Get active
    active = await account_repo.get_all_active(db_session)
    assert len(active) == 1
    assert active[0].id == acct1.id

    # Get all
    all_accts = await account_repo.get_all(db_session)
    assert len(all_accts) == 2

    # Delete
    deleted = await account_repo.delete(db_session, acct1.id)
    assert deleted is True

    # Try deleting again
    deleted_again = await account_repo.delete(db_session, acct1.id)
    assert deleted_again is False

    all_accts = await account_repo.get_all(db_session)
    assert len(all_accts) == 1
