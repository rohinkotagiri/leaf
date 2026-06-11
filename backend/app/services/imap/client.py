"""Base email client and IMAP implementation.

BaseEmailClient defines the abstract interface for all email providers.
ImapClient provides the concrete implementation using imapclient.

All imapclient calls are wrapped in run_in_executor() since imapclient
is synchronous — this prevents blocking the async event loop.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from functools import partial
from typing import Any

import imapclient

from app.config import settings
from app.schemas.email import EmailMessage
from app.services.imap.parser import EmailParser

logger = logging.getLogger(__name__)


class BaseEmailClient(ABC):
    """Abstract base class defining the email client interface.

    All provider-specific clients (Gmail, Outlook, generic IMAP)
    must implement these methods.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the email server."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection to the email server."""

    @abstractmethod
    async def list_folders(self) -> list[str]:
        """List all available folders/mailboxes."""

    @abstractmethod
    async def fetch_emails(
        self,
        folder: str = "INBOX",
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[EmailMessage]:
        """Fetch emails from the specified folder.

        Args:
            folder: IMAP folder to fetch from.
            limit: Maximum number of emails to fetch.
            since: Only fetch emails after this date.

        Returns:
            List of parsed EmailMessage objects.
        """

    @abstractmethod
    async def fetch_email_by_uid(self, uid: int) -> EmailMessage | None:
        """Fetch a single email by its IMAP UID."""

    @abstractmethod
    async def mark_as_read(self, uid: int) -> None:
        """Mark an email as read (add \\Seen flag)."""

    @abstractmethod
    async def move_email(self, uid: int, target_folder: str) -> None:
        """Move an email to another folder."""

    @abstractmethod
    async def delete_email(self, uid: int) -> None:
        """Delete an email (move to Trash or expunge)."""

    @abstractmethod
    async def idle_start(self) -> None:
        """Start IMAP IDLE mode for real-time push notifications."""

    @abstractmethod
    async def idle_check(self, timeout: int = 30) -> list:
        """Check for IDLE notifications."""

    @abstractmethod
    async def idle_done(self) -> None:
        """Exit IMAP IDLE mode."""

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if the connection is alive."""


class ImapClient(BaseEmailClient):
    """Concrete IMAP client using imapclient.

    All synchronous imapclient operations are run in a thread executor
    to avoid blocking the async event loop.
    """

    def __init__(
        self,
        host: str,
        port: int = 993,
        use_ssl: bool = True,
        account_id: str = "",
        timeout: int | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.account_id = account_id
        self.timeout = timeout or settings.IMAP_TIMEOUT

        self._client: imapclient.IMAPClient | None = None
        self._parser = EmailParser()
        self._current_folder: str | None = None

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous function in the default thread executor."""
        loop = asyncio.get_event_loop()
        if kwargs:
            return await loop.run_in_executor(None, partial(func, *args, **kwargs))
        return await loop.run_in_executor(None, func, *args)

    def _ensure_client(self) -> imapclient.IMAPClient:
        """Return the underlying client, raising if not connected."""
        if self._client is None:
            raise ConnectionError("IMAP client is not connected. Call connect() first.")
        return self._client

    # ── Connection management ─────────────────────────────────────────

    async def connect(self) -> None:
        """Connect to the IMAP server."""
        logger.info(
            "Connecting to IMAP server %s:%d (SSL=%s) for account %s",
            self.host,
            self.port,
            self.use_ssl,
            self.account_id,
        )
        try:
            self._client = await self._run_sync(
                imapclient.IMAPClient,
                self.host,
                port=self.port,
                ssl=self.use_ssl,
                timeout=self.timeout,
            )
            logger.info("IMAP connection established to %s", self.host)
        except Exception:
            logger.exception("Failed to connect to IMAP server %s:%d", self.host, self.port)
            raise

    async def authenticate(self, username: str, password: str) -> None:
        """Authenticate with username/password (PLAIN login).

        For OAuth2 authentication, subclasses override this method.
        """
        client = self._ensure_client()
        logger.info("Authenticating user %s on %s", username, self.host)
        try:
            await self._run_sync(client.login, username, password)
            logger.info("Authentication successful for %s", username)
        except Exception:
            logger.exception("Authentication failed for %s on %s", username, self.host)
            raise

    async def disconnect(self) -> None:
        """Disconnect from the IMAP server."""
        if self._client is not None:
            try:
                await self._run_sync(self._client.logout)
                logger.info("Disconnected from %s", self.host)
            except Exception:
                logger.warning("Error during IMAP disconnect from %s", self.host)
            finally:
                self._client = None
                self._current_folder = None

    async def is_connected(self) -> bool:
        """Check if the connection is alive via NOOP."""
        if self._client is None:
            return False
        try:
            await self._run_sync(self._client.noop)
            return True
        except Exception:
            return False

    async def _ensure_connected(self) -> None:
        """Verify connection is alive, reconnect if needed."""
        if not await self.is_connected():
            logger.warning("IMAP connection lost to %s, reconnecting...", self.host)
            await self.connect()

    # ── Folder operations ─────────────────────────────────────────────

    async def list_folders(self) -> list[str]:
        """List all available IMAP folders."""
        await self._ensure_connected()
        client = self._ensure_client()

        logger.debug("Listing folders on %s", self.host)
        raw_folders = await self._run_sync(client.list_folders)

        folders: list[str] = []
        for _flags, _delimiter, name in raw_folders:
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            folders.append(name)

        logger.info("Found %d folders on %s", len(folders), self.host)
        return folders

    async def _select_folder(self, folder: str) -> None:
        """Select a folder, skipping if already selected."""
        if self._current_folder == folder:
            return

        client = self._ensure_client()
        await self._run_sync(client.select_folder, folder)
        self._current_folder = folder
        logger.debug("Selected folder: %s", folder)

    # ── Email fetch operations ────────────────────────────────────────

    async def fetch_emails(
        self,
        folder: str = "INBOX",
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[EmailMessage]:
        """Fetch emails from the specified folder."""
        await self._ensure_connected()
        client = self._ensure_client()
        await self._select_folder(folder)

        # Build search criteria
        criteria: list[str | bytes] = []
        if since:
            date_str = since.strftime("%d-%b-%Y")
            criteria.extend(["SINCE", date_str])
        else:
            criteria.append("ALL")

        logger.info(
            "Searching emails in %s with criteria %s (limit=%d)",
            folder,
            criteria,
            limit,
        )

        uids = await self._run_sync(client.search, criteria)

        # Take the most recent UIDs (highest UIDs = most recent)
        uids = sorted(uids)[-limit:]

        if not uids:
            logger.info("No emails found in %s", folder)
            return []

        logger.info("Fetching %d emails from %s", len(uids), folder)

        # Fetch in batches to avoid IMAP timeout on large fetches
        batch_size = settings.IMAP_BATCH_SIZE
        emails: list[EmailMessage] = []

        for i in range(0, len(uids), batch_size):
            batch_uids = uids[i : i + batch_size]
            raw_messages = await self._run_sync(
                client.fetch, batch_uids, ["RFC822", "FLAGS"]
            )

            for uid_val, data in raw_messages.items():
                try:
                    raw_bytes = data.get(b"RFC822", b"")
                    flags = [
                        f.decode("utf-8") if isinstance(f, bytes) else str(f)
                        for f in data.get(b"FLAGS", ())
                    ]

                    parsed = self._parser.parse(
                        raw_bytes=raw_bytes,
                        account_id=self.account_id,
                        folder=folder,
                        uid=int(uid_val),
                    )
                    parsed.flags = flags
                    emails.append(parsed)
                except Exception:
                    logger.exception("Failed to parse email UID %s in %s", uid_val, folder)

        logger.info("Successfully fetched %d emails from %s", len(emails), folder)
        return emails

    async def fetch_email_by_uid(self, uid: int) -> EmailMessage | None:
        """Fetch a single email by its IMAP UID."""
        await self._ensure_connected()
        client = self._ensure_client()

        logger.debug("Fetching email UID %d", uid)

        try:
            raw_messages = await self._run_sync(
                client.fetch, [uid], ["RFC822", "FLAGS"]
            )

            if uid not in raw_messages:
                logger.warning("Email UID %d not found", uid)
                return None

            data = raw_messages[uid]
            raw_bytes = data.get(b"RFC822", b"")
            flags = [
                f.decode("utf-8") if isinstance(f, bytes) else str(f)
                for f in data.get(b"FLAGS", ())
            ]

            parsed = self._parser.parse(
                raw_bytes=raw_bytes,
                account_id=self.account_id,
                folder=self._current_folder or "INBOX",
                uid=uid,
            )
            parsed.flags = flags
            return parsed
        except Exception:
            logger.exception("Failed to fetch email UID %d", uid)
            return None

    # ── Flag / move / delete operations ───────────────────────────────

    async def mark_as_read(self, uid: int) -> None:
        """Mark an email as read."""
        await self._ensure_connected()
        client = self._ensure_client()

        logger.debug("Marking UID %d as read", uid)
        await self._run_sync(client.add_flags, [uid], [imapclient.SEEN])

    async def move_email(self, uid: int, target_folder: str) -> None:
        """Move an email to another folder."""
        await self._ensure_connected()
        client = self._ensure_client()

        logger.debug("Moving UID %d to %s", uid, target_folder)
        await self._run_sync(client.move, [uid], target_folder)

    async def delete_email(self, uid: int) -> None:
        """Delete an email (add \\Deleted flag and expunge)."""
        await self._ensure_connected()
        client = self._ensure_client()

        logger.debug("Deleting UID %d", uid)
        await self._run_sync(client.delete_messages, [uid])
        await self._run_sync(client.expunge)

    # ── IDLE operations (stubbed — fully implemented in sync worker) ──

    async def idle_start(self) -> None:
        """Start IMAP IDLE mode."""
        client = self._ensure_client()
        logger.debug("Starting IDLE on %s", self.host)
        await self._run_sync(client.idle)

    async def idle_check(self, timeout: int = 30) -> list:
        """Check for IDLE notifications."""
        client = self._ensure_client()
        responses = await self._run_sync(client.idle_check, timeout=timeout)
        return list(responses) if responses else []

    async def idle_done(self) -> None:
        """Exit IDLE mode."""
        client = self._ensure_client()
        await self._run_sync(client.idle_done)
        logger.debug("IDLE done on %s", self.host)
