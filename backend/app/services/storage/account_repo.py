"""Account repository — async CRUD for email account management."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.schemas.account import AccountCreate

logger = logging.getLogger(__name__)


class AccountRepository:
    """Async repository for Account CRUD operations."""

    async def create(
        self,
        session: AsyncSession,
        data: AccountCreate,
    ) -> Account:
        """Create a new email account."""
        account = Account(
            email_address=data.email_address,
            display_name=data.display_name,
            provider=data.provider,
            imap_host=data.imap_host,
            imap_port=data.imap_port,
            use_ssl=data.use_ssl,
            credentials_key=data.credentials_key,
        )
        session.add(account)
        await session.flush()

        logger.info("Created account %s (%s)", account.id[:8], account.email_address)
        return account

    async def get_by_id(
        self, session: AsyncSession, account_id: str
    ) -> Account | None:
        """Get an account by its ID."""
        return await session.get(Account, account_id)

    async def get_by_email(
        self, session: AsyncSession, email_address: str
    ) -> Account | None:
        """Get an account by email address."""
        stmt = select(Account).where(Account.email_address == email_address)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_active(self, session: AsyncSession) -> list[Account]:
        """Get all accounts with sync enabled."""
        stmt = (
            select(Account)
            .where(Account.sync_enabled == True)  # noqa: E712
            .order_by(Account.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_all(self, session: AsyncSession) -> list[Account]:
        """Get all accounts."""
        stmt = select(Account).order_by(Account.created_at.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        session: AsyncSession,
        account_id: str,
        **updates: object,
    ) -> None:
        """Update specific fields of an account."""
        account = await session.get(Account, account_id)
        if account and updates:
            for key, val in updates.items():
                setattr(account, key, val)
            await session.flush()
            logger.debug("Updated account %s: %s", account_id[:8], list(updates.keys()))

    async def update_sync_status(
        self,
        session: AsyncSession,
        account_id: str,
        last_sync_at: datetime,
        sync_cursor: str | None = None,
    ) -> None:
        """Update the sync status after an IMAP sync completes."""
        account = await session.get(Account, account_id)
        if account:
            account.last_sync_at = last_sync_at
            if sync_cursor is not None:
                account.sync_cursor = sync_cursor
            await session.flush()
            logger.debug("Updated sync status for account %s", account_id[:8])

    async def delete(self, session: AsyncSession, account_id: str) -> bool:
        """Delete an account and all its related data (cascade).

        Returns:
            True if the account existed and was deleted.
        """
        account = await session.get(Account, account_id)
        if account is None:
            return False

        await session.delete(account)
        await session.flush()
        logger.info("Deleted account %s", account_id[:8])
        return True
