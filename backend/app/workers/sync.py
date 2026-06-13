"""Worker for real-time and scheduled email synchronization via IMAP and IMAP IDLE."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.account import Account, ProviderType
from app.services.imap import AccountCredentialStore, create_email_client
from app.services.pipeline import AnalysisPipeline, IngestionPipeline

logger = logging.getLogger(__name__)


class SyncWorker:
    """Manages IMAP synchronization for all accounts, handling polling and IMAP IDLE."""

    # Active IDLE tasks: account_id -> asyncio.Task
    _idle_tasks: dict[str, asyncio.Task] = {}
    _running_syncs: set[str] = set()

    def __init__(self) -> None:
        self.ingestion_pipeline = IngestionPipeline()
        self.analysis_pipeline = AnalysisPipeline()
        self.credential_store = AccountCredentialStore()

    async def sync_all_accounts(self) -> None:
        """Trigger incremental sync for all active accounts."""
        logger.info("Starting sync for all active accounts...")
        async with async_session_factory() as session:
            stmt = select(Account).where(Account.sync_enabled == True)  # noqa: E712
            res = await session.execute(stmt)
            accounts = list(res.scalars().all())

        for account in accounts:
            asyncio.create_task(self.sync_account(account.id))

    async def sync_account(self, account_id: str, force: bool = False) -> None:
        """Perform an incremental sync for a single account."""
        if account_id in self._running_syncs:
            logger.warning("Sync already running for account %s. Skipping.", account_id)
            return

        self._running_syncs.add(account_id)
        logger.info("Starting sync for account: %s", account_id)

        try:
            async with async_session_factory() as session:
                # Fetch fresh account record
                account = await session.get(Account, account_id)
                if not account:
                    logger.error("Account %s not found for sync", account_id)
                    return

                if not account.sync_enabled and not force:
                    logger.info("Sync disabled for account %s. Skipping.", account_id)
                    return

                # Build client and authenticate
                client = create_email_client(account, self.credential_store)
                await client.connect()

                try:
                    if account.provider == ProviderType.GENERIC:
                        password = self.credential_store.get_password(account.id)
                        if not password:
                            raise ValueError(f"No password stored for generic IMAP account {account.id}")
                        await client.authenticate(account.email_address, password)
                    else:
                        await client.authenticate()

                    # Determine since time
                    since_date = None
                    if account.sync_cursor:
                        try:
                            since_date = datetime.fromisoformat(account.sync_cursor)
                        except Exception:
                            logger.warning("Invalid sync cursor for account %s: %s", account_id, account.sync_cursor)

                    if not since_date:
                        # Default to 30 days ago
                        since_date = datetime.now(UTC) - timedelta(days=30)

                    # Fetch emails
                    logger.info("Fetching new emails since %s for account %s", since_date.isoformat(), account.email_address)
                    new_emails = await client.fetch_emails(
                        folder="INBOX",
                        limit=settings.MAX_EMAILS_PER_SYNC,
                        since=since_date,
                    )

                    # Ingest and analyze each email
                    for email_msg in new_emails:
                        # Run ingestion (dedup, sql save, chroma write, analysis enqueue)
                        ingest_res = await self.ingestion_pipeline.ingest_email(session, email_msg)

                        # Commit the ingestion transaction before analysis starts
                        await session.commit()

                        # If ingestion enqueued the email successfully, trigger analysis
                        if "enqueue" in ingest_res.stages_completed:
                            # Start a separate transaction for analysis
                            async with async_session_factory() as analysis_session:
                                try:
                                    analysis_res = await self.analysis_pipeline.analyze_email(analysis_session, email_msg.id)
                                    if analysis_res.success:
                                        await analysis_session.commit()
                                    else:
                                        await analysis_session.rollback()
                                except Exception:
                                    await analysis_session.rollback()
                                    logger.exception("Failed to run analysis pipeline for email %s during sync", email_msg.id)

                    # Update cursor and last sync time
                    # We set the cursor to 1 second ago to avoid clock drift issues
                    next_cursor = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
                    account.sync_cursor = next_cursor
                    account.last_sync_at = datetime.now(UTC)
                    await session.commit()
                    logger.info("Completed sync for account %s. Cursor updated to %s.", account.email_address, next_cursor)

                finally:
                    await client.disconnect()

        except Exception:
            logger.exception("Failed to synchronize account %s", account_id)
        finally:
            self._running_syncs.discard(account_id)

    async def start_idle_loop(self, account_id: str) -> None:
        """Start a background loop maintaining an IMAP IDLE connection for real-time sync."""
        if account_id in self._idle_tasks:
            logger.warning("IDLE task already running for account %s", account_id)
            return

        task = asyncio.create_task(self._run_idle_loop(account_id))
        self._idle_tasks[account_id] = task
        logger.info("IDLE loop scheduled for account: %s", account_id)

    async def stop_idle_loop(self, account_id: str) -> None:
        """Cancel the active IDLE loop task for an account."""
        task = self._idle_tasks.pop(account_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("IDLE loop stopped for account: %s", account_id)

    async def stop_all_idle_loops(self) -> None:
        """Stop all background IDLE loops."""
        account_ids = list(self._idle_tasks.keys())
        for aid in account_ids:
            await self.stop_idle_loop(aid)

    async def _run_idle_loop(self, account_id: str) -> None:
        """Internal background loop managing connection reconnects and checking for IDLE updates."""
        retry_delay = 5.0

        while True:
            try:
                async with async_session_factory() as session:
                    account = await session.get(Account, account_id)
                    if not account or not account.sync_enabled:
                        logger.info("Stopping IDLE loop for %s — account disabled or deleted", account_id)
                        break
                    email_address = account.email_address

                logger.info("Starting IDLE connection for %s", email_address)
                client = create_email_client(account, self.credential_store)
                await client.connect()

                try:
                    if account.provider == ProviderType.GENERIC:
                        password = self.credential_store.get_password(account.id)
                        if not password:
                            raise ValueError(f"No password stored for generic IMAP account {account.id}")
                        await client.authenticate(account.email_address, password)
                    else:
                        await client.authenticate()

                    # Select inbox first
                    await client._select_folder("INBOX")
                    retry_delay = 5.0  # Reset retry delay on successful auth

                    logger.info("Entering IDLE state for %s", email_address)
                    await client.idle_start()

                    while True:
                        # Check IDLE responses (non-blocking)
                        # We use 29s timeout as standard IMAP IDLE protocol requires refreshing every 29 mins,
                        # but check frequently to keep socket alive and respond to new mails.
                        responses = await client.idle_check(timeout=30)

                        # If we have any response (meaning event happened like EXISTS, FETCH, etc.)
                        # Or if we just want to run periodic check
                        if responses:
                            logger.info("IDLE notification received for %s: %s", email_address, responses)
                            await client.idle_done()

                            # Perform full sync to fetch new messages
                            await self.sync_account(account_id)

                            # Restart IDLE
                            await client.idle_start()

                finally:
                    # Clean cleanup
                    try:
                        await client.idle_done()
                    except Exception:
                        pass
                    await client.disconnect()

            except asyncio.CancelledError:
                logger.info("IDLE loop cancelled for account %s", account_id)
                raise
            except Exception as e:
                logger.warning(
                    "Error in IDLE loop for account %s: %s. Reconnecting in %.1fs",
                    account_id,
                    str(e),
                    retry_delay,
                    exc_info=True
                )
                await asyncio.sleep(retry_delay)
                # Exponential backoff
                retry_delay = min(retry_delay * 2, 300.0)
