"""Integration tests for ImapClient — uses mocked imapclient.IMAPClient."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.imap.client import ImapClient
from app.services.imap.pool import ConnectionPool


class TestImapClient:
    """Integration tests for the IMAP client with a mocked IMAP backend."""

    def setup_method(self) -> None:
        self.client = ImapClient(
            host="imap.example.com",
            port=993,
            use_ssl=True,
            account_id="test-account",
        )

    @pytest.fixture
    def mock_imap(self) -> MagicMock:
        """Create a mock IMAPClient instance."""
        mock = MagicMock()
        mock.login.return_value = b"OK"
        mock.logout.return_value = b"OK"
        mock.noop.return_value = (b"OK", [])
        mock.list_folders.return_value = [
            ((b"\\HasNoChildren",), b"/", "INBOX"),
            ((b"\\HasNoChildren",), b"/", "Sent"),
            ((b"\\HasNoChildren", b"\\Trash"), b"/", "Trash"),
        ]
        mock.select_folder.return_value = {b"EXISTS": 10}
        mock.search.return_value = [1, 2, 3]
        mock.fetch.return_value = {
            1: {
                b"RFC822": (
                    b"From: alice@example.com\r\n"
                    b"To: bob@example.com\r\n"
                    b"Subject: Test Email 1\r\n"
                    b"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
                    b"Message-ID: <test1@example.com>\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"\r\n"
                    b"Body of email 1.\r\n"
                ),
                b"FLAGS": (b"\\Seen",),
            },
            2: {
                b"RFC822": (
                    b"From: charlie@example.com\r\n"
                    b"To: bob@example.com\r\n"
                    b"Subject: Test Email 2\r\n"
                    b"Date: Tue, 02 Jan 2024 09:00:00 +0000\r\n"
                    b"Message-ID: <test2@example.com>\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"\r\n"
                    b"Body of email 2.\r\n"
                ),
                b"FLAGS": (),
            },
            3: {
                b"RFC822": (
                    b"From: dave@example.com\r\n"
                    b"To: bob@example.com\r\n"
                    b"Subject: Test Email 3\r\n"
                    b"Date: Wed, 03 Jan 2024 15:00:00 +0000\r\n"
                    b"Message-ID: <test3@example.com>\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"\r\n"
                    b"Body of email 3.\r\n"
                ),
                b"FLAGS": (b"\\Seen", b"\\Flagged"),
            },
        }
        return mock

    # ── Connection tests ──────────────────────────────────────────────

    @patch("app.services.imap.client.imapclient.IMAPClient")
    async def test_connect(self, mock_imap_class: MagicMock) -> None:
        """Client should create an IMAPClient on connect."""
        mock_instance = MagicMock()
        mock_imap_class.return_value = mock_instance

        await self.client.connect()

        mock_imap_class.assert_called_once_with(
            "imap.example.com", port=993, ssl=True, timeout=30
        )

    @patch("app.services.imap.client.imapclient.IMAPClient")
    async def test_disconnect(self, mock_imap_class: MagicMock) -> None:
        """Client should logout on disconnect."""
        mock_instance = MagicMock()
        mock_imap_class.return_value = mock_instance

        await self.client.connect()
        await self.client.disconnect()

        mock_instance.logout.assert_called_once()

    @patch("app.services.imap.client.imapclient.IMAPClient")
    async def test_is_connected(self, mock_imap_class: MagicMock) -> None:
        """is_connected should return True when NOOP succeeds."""
        mock_instance = MagicMock()
        mock_imap_class.return_value = mock_instance
        mock_instance.noop.return_value = (b"OK", [])

        await self.client.connect()
        assert await self.client.is_connected()

    async def test_is_connected_when_not_connected(self) -> None:
        """is_connected should return False when no connection exists."""
        assert not await self.client.is_connected()

    # ── Folder operations ─────────────────────────────────────────────

    @patch("app.services.imap.client.imapclient.IMAPClient")
    async def test_list_folders(self, mock_imap_class: MagicMock, mock_imap: MagicMock) -> None:
        """list_folders should return folder names as strings."""
        mock_imap_class.return_value = mock_imap

        await self.client.connect()
        folders = await self.client.list_folders()

        assert "INBOX" in folders
        assert "Sent" in folders
        assert "Trash" in folders
        assert len(folders) == 3

    # ── Email fetch operations ────────────────────────────────────────

    @patch("app.services.imap.client.imapclient.IMAPClient")
    async def test_fetch_emails(self, mock_imap_class: MagicMock, mock_imap: MagicMock) -> None:
        """fetch_emails should parse raw messages into EmailMessage objects."""
        mock_imap_class.return_value = mock_imap

        await self.client.connect()
        emails = await self.client.fetch_emails(folder="INBOX", limit=10)

        assert len(emails) == 3
        assert emails[0].subject == "Test Email 1"
        assert emails[0].sender_email == "alice@example.com"
        assert "Body of email 1" in emails[0].body_text

    @patch("app.services.imap.client.imapclient.IMAPClient")
    async def test_fetch_emails_with_since(
        self, mock_imap_class: MagicMock, mock_imap: MagicMock
    ) -> None:
        """fetch_emails with since parameter should use SINCE criteria."""
        mock_imap_class.return_value = mock_imap

        await self.client.connect()
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        await self.client.fetch_emails(folder="INBOX", limit=10, since=since)

        # Verify search was called with SINCE criteria
        search_call = mock_imap.search.call_args
        criteria = search_call[0][0]
        assert "SINCE" in criteria

    @patch("app.services.imap.client.imapclient.IMAPClient")
    async def test_fetch_email_by_uid(
        self, mock_imap_class: MagicMock, mock_imap: MagicMock
    ) -> None:
        """fetch_email_by_uid should return a single parsed email."""
        mock_imap.fetch.return_value = {
            42: {
                b"RFC822": (
                    b"From: test@example.com\r\n"
                    b"To: receiver@example.com\r\n"
                    b"Subject: Single Fetch\r\n"
                    b"Date: Thu, 04 Jan 2024 10:00:00 +0000\r\n"
                    b"Message-ID: <single@example.com>\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"\r\n"
                    b"Single body.\r\n"
                ),
                b"FLAGS": (b"\\Seen",),
            }
        }
        mock_imap_class.return_value = mock_imap

        await self.client.connect()
        await self.client._select_folder("INBOX")
        email = await self.client.fetch_email_by_uid(42)

        assert email is not None
        assert email.subject == "Single Fetch"
        assert email.uid == 42

    @patch("app.services.imap.client.imapclient.IMAPClient")
    async def test_fetch_email_by_uid_not_found(
        self, mock_imap_class: MagicMock, mock_imap: MagicMock
    ) -> None:
        """fetch_email_by_uid should return None when UID doesn't exist."""
        mock_imap.fetch.return_value = {}
        mock_imap_class.return_value = mock_imap

        await self.client.connect()
        email = await self.client.fetch_email_by_uid(999)

        assert email is None

    # ── Auto-reconnect ────────────────────────────────────────────────

    @patch("app.services.imap.client.imapclient.IMAPClient")
    async def test_auto_reconnect_on_stale_connection(
        self, mock_imap_class: MagicMock
    ) -> None:
        """Should reconnect automatically when NOOP fails."""
        mock1 = MagicMock()
        mock2 = MagicMock()
        mock2.noop.return_value = (b"OK", [])
        mock2.list_folders.return_value = [((b"\\HasNoChildren",), b"/", "INBOX")]

        # First connect returns mock1 (which will fail noop), second returns mock2
        mock_imap_class.side_effect = [mock1, mock2]

        await self.client.connect()
        # Simulate stale connection
        mock1.noop.side_effect = OSError("Connection reset")

        # This should trigger reconnect
        folders = await self.client.list_folders()
        assert "INBOX" in folders


class TestConnectionPool:
    """Tests for the IMAP connection pool."""

    async def test_pool_acquire_and_release(self) -> None:
        """Basic acquire/release cycle with a mock client."""
        pool = ConnectionPool(max_per_account=2)

        mock_client = AsyncMock()
        mock_client.is_connected = AsyncMock(return_value=True)

        # Release a client into the pool
        pool._pools["acct1"].append(mock_client)

        # Acquire should return it
        client = await pool.acquire("acct1")
        assert client is mock_client

        # Release it back
        await pool.release("acct1", client)
        assert len(pool._pools["acct1"]) == 1

    async def test_pool_discards_stale_connections(self) -> None:
        """Stale connections should be discarded, not returned."""
        pool = ConnectionPool(max_per_account=2)

        stale_client = AsyncMock()
        stale_client.is_connected = AsyncMock(return_value=False)
        stale_client.disconnect = AsyncMock()

        pool._pools["acct1"].append(stale_client)

        # Should raise because after discarding stale, no factory provided
        with pytest.raises(ValueError, match="no client_factory"):
            await pool.acquire("acct1")

    async def test_pool_max_connections(self) -> None:
        """Should raise when max connections per account is exceeded."""
        pool = ConnectionPool(max_per_account=1)
        pool._in_use["acct1"] = 1

        with pytest.raises(ConnectionError, match="exhausted"):
            await pool.acquire("acct1")

    async def test_pool_close_all(self) -> None:
        """close_all should disconnect all pooled connections."""
        pool = ConnectionPool()

        mock1 = AsyncMock()
        mock2 = AsyncMock()

        pool._pools["acct1"].append(mock1)
        pool._pools["acct2"].append(mock2)

        await pool.close_all()

        mock1.disconnect.assert_called_once()
        mock2.disconnect.assert_called_once()
        assert len(pool._pools["acct1"]) == 0
        assert len(pool._pools["acct2"]) == 0

    async def test_pool_stats(self) -> None:
        """stats() should return correct per-account counts."""
        pool = ConnectionPool()

        mock = AsyncMock()
        pool._pools["acct1"].append(mock)
        pool._in_use["acct1"] = 1

        stats = pool.stats()
        assert stats["acct1"]["pooled"] == 1
        assert stats["acct1"]["in_use"] == 1
