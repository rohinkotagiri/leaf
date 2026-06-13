"""Integration tests for email client factory and OAuth clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.account import Account, ProviderType
from app.services.imap import create_email_client
from app.services.imap.client import ImapClient
from app.services.imap.gmail import GmailClient
from app.services.imap.outlook import OutlookClient


def _make_account(provider: ProviderType, **kwargs: object) -> Account:
    account = Account(
        email_address="user@example.com",
        provider=provider,
        imap_host=kwargs.get("imap_host", ""),
        imap_port=kwargs.get("imap_port", 993),
        use_ssl=kwargs.get("use_ssl", True),
        credentials_key=f"oauth:{kwargs.get('imap_host', 'default')}" if provider != ProviderType.GENERIC else None,
    )
    return account


class TestCreateEmailClient:
    """Factory should return the correct client type per provider."""

    def test_gmail_client(self) -> None:
        account = _make_account(ProviderType.GMAIL)
        client = create_email_client(account)
        assert isinstance(client, GmailClient)
        assert client.host == "imap.gmail.com"

    def test_outlook_client(self) -> None:
        account = _make_account(ProviderType.OUTLOOK)
        client = create_email_client(account)
        assert isinstance(client, OutlookClient)
        assert client.host == "outlook.office365.com"

    def test_generic_imap_client(self) -> None:
        account = _make_account(
            ProviderType.GENERIC,
            imap_host="mail.example.com",
            imap_port=143,
            use_ssl=False,
        )
        client = create_email_client(account)
        assert isinstance(client, ImapClient)
        assert client.host == "mail.example.com"
        assert client.port == 143
        assert client.use_ssl is False


class TestGmailClient:
    """Gmail OAuth2 authentication tests."""

    async def test_gmail_oauth2_login(self) -> None:
        mock_instance = MagicMock()
        client = GmailClient(
            account_id="gmail-acct",
            email_address="user@gmail.com",
        )
        client._client = mock_instance

        async def run_sync(fn, *args, **kwargs):  # noqa: ANN001, ANN202
            return fn(*args, **kwargs)

        with (
            patch.object(client, "_run_sync", side_effect=run_sync),
            patch.object(client._credential_store, "get_oauth_tokens") as mock_tokens,
            patch.object(client._credential_store, "store_oauth_tokens"),
        ):
            mock_tokens.return_value = {
                "access_token": "test_token",
                "refresh_token": "refresh",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "cid",
                "client_secret": "secret",
            }
            await client.authenticate()

        mock_instance.oauth2_login.assert_called_once_with("user@gmail.com", "test_token")


class TestOutlookClient:
    """Outlook MSAL device flow tests."""

    async def test_outlook_device_flow_initiate(self) -> None:
        mock_app = MagicMock()
        mock_app.initiate_device_flow.return_value = {
            "user_code": "ABCD1234",
            "verification_uri": "https://microsoft.com/devicelogin",
        }

        client = OutlookClient(
            account_id="outlook-acct",
            email_address="user@outlook.com",
            client_id="test-client-id",
        )

        with patch.object(client, "_get_msal_app", return_value=mock_app):
            with patch.object(client, "_run_sync", new=AsyncMock(side_effect=lambda fn, *a, **k: fn(*a, **k))):
                flow = await client.initiate_device_flow()

        assert flow["user_code"] == "ABCD1234"

    async def test_outlook_device_flow_complete(self) -> None:
        mock_app = MagicMock()
        mock_app.acquire_token_by_device_flow.return_value = {
            "access_token": "outlook_token",
            "refresh_token": "outlook_refresh",
        }

        client = OutlookClient(
            account_id="outlook-acct",
            email_address="user@outlook.com",
            client_id="test-client-id",
        )

        with patch.object(client, "_get_msal_app", return_value=mock_app):
            with patch.object(client, "_run_sync", new=AsyncMock(side_effect=lambda fn, *a, **k: fn(*a, **k))):
                with patch.object(client._credential_store, "store_oauth_tokens") as mock_store:
                    token = await client.complete_device_flow({"device_code": "abc"})
                    assert token == "outlook_token"
                    mock_store.assert_called_once()

    async def test_outlook_device_flow_failure(self) -> None:
        mock_app = MagicMock()
        mock_app.acquire_token_by_device_flow.return_value = {
            "error_description": "User cancelled",
        }

        client = OutlookClient(
            account_id="outlook-acct",
            email_address="user@outlook.com",
            client_id="test-client-id",
        )

        with patch.object(client, "_get_msal_app", return_value=mock_app):
            with patch.object(client, "_run_sync", new=AsyncMock(side_effect=lambda fn, *a, **k: fn(*a, **k))):
                with pytest.raises(ValueError, match="Device flow failed"):
                    await client.complete_device_flow({"device_code": "abc"})
