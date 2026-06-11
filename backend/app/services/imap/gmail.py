"""Gmail IMAP client with OAuth2 XOAUTH2 authentication.

Uses google-auth-oauthlib for token management and refreshes
tokens automatically when they expire.
"""

from __future__ import annotations

import base64
import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.services.imap.client import ImapClient
from app.services.imap.credential_store import AccountCredentialStore

logger = logging.getLogger(__name__)

# Gmail IMAP defaults
GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993

# OAuth2 scopes required for IMAP access
GMAIL_SCOPES = [
    "https://mail.google.com/",
]


class GmailClient(ImapClient):
    """Gmail IMAP client with OAuth2 authentication.

    Authenticates using XOAUTH2 SASL mechanism instead of plain password.
    Tokens are stored in the system keyring via AccountCredentialStore.
    """

    def __init__(
        self,
        account_id: str,
        email_address: str,
        credential_store: AccountCredentialStore | None = None,
    ) -> None:
        super().__init__(
            host=GMAIL_IMAP_HOST,
            port=GMAIL_IMAP_PORT,
            use_ssl=True,
            account_id=account_id,
        )
        self.email_address = email_address
        self._credential_store = credential_store or AccountCredentialStore()
        self._credentials: Credentials | None = None

    async def authenticate(self, username: str = "", password: str = "") -> None:
        """Authenticate with Gmail using OAuth2 XOAUTH2.

        Ignores username/password parameters — uses stored OAuth tokens.
        """
        client = self._ensure_client()
        access_token = await self._get_access_token()

        logger.info("Authenticating %s via XOAUTH2", self.email_address)

        try:
            # Build XOAUTH2 string per RFC 7628
            auth_string = self._build_xoauth2_string(self.email_address, access_token)
            await self._run_sync(client.oauth2_login, self.email_address, access_token)
            logger.info("Gmail OAuth2 authentication successful for %s", self.email_address)
        except Exception as e:
            # If auth fails, try refreshing the token and retry once
            if "AUTHENTICATIONFAILED" in str(e) or "Invalid credentials" in str(e):
                logger.warning("OAuth2 auth failed, forcing token refresh for %s", self.email_address)
                access_token = await self._refresh_token(force=True)
                await self._run_sync(client.oauth2_login, self.email_address, access_token)
                logger.info("Gmail OAuth2 re-authentication successful for %s", self.email_address)
            else:
                logger.exception("Gmail authentication failed for %s", self.email_address)
                raise

    async def _get_access_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        tokens = self._credential_store.get_oauth_tokens(self.account_id)
        if not tokens:
            raise ValueError(
                f"No OAuth tokens found for account {self.account_id}. "
                "Run the OAuth2 authorization flow first."
            )

        self._credentials = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
        )

        # Refresh if expired
        if self._credentials.expired and self._credentials.refresh_token:
            return await self._refresh_token()

        return self._credentials.token

    async def _refresh_token(self, force: bool = False) -> str:
        """Refresh the OAuth2 access token."""
        if self._credentials is None:
            raise ValueError("No credentials loaded — call _get_access_token first")

        logger.info("Refreshing OAuth2 token for %s", self.email_address)

        if force or self._credentials.expired:
            await self._run_sync(self._credentials.refresh, Request())

        # Update stored tokens
        self._credential_store.store_oauth_tokens(
            self.account_id,
            {
                "access_token": self._credentials.token,
                "refresh_token": self._credentials.refresh_token,
                "token_uri": self._credentials.token_uri,
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
            },
        )

        logger.info("OAuth2 token refreshed for %s", self.email_address)
        return self._credentials.token

    @staticmethod
    def _build_xoauth2_string(email_address: str, access_token: str) -> str:
        """Build the XOAUTH2 authentication string.

        Format: user={email}\\x01auth=Bearer {token}\\x01\\x01
        """
        auth_string = f"user={email_address}\x01auth=Bearer {access_token}\x01\x01"
        return base64.b64encode(auth_string.encode("ascii")).decode("ascii")
