"""Outlook IMAP client with MSAL OAuth2 authentication.

Uses MSAL device flow for authentication and caches tokens
via the system keyring through AccountCredentialStore.
"""

from __future__ import annotations

import logging

import msal

from app.services.imap.client import ImapClient
from app.services.imap.credential_store import AccountCredentialStore

logger = logging.getLogger(__name__)

# Outlook IMAP defaults
OUTLOOK_IMAP_HOST = "outlook.office365.com"
OUTLOOK_IMAP_PORT = 993

# OAuth2 scopes for Outlook IMAP
OUTLOOK_SCOPES = [
    "https://outlook.office365.com/IMAP.AccessAsUser.All",
]


class OutlookClient(ImapClient):
    """Outlook IMAP client with MSAL OAuth2 authentication.

    Uses Microsoft Authentication Library (MSAL) for device flow auth
    and XOAUTH2 for IMAP authentication.
    """

    def __init__(
        self,
        account_id: str,
        email_address: str,
        client_id: str = "",
        authority: str = "https://login.microsoftonline.com/common",
        credential_store: AccountCredentialStore | None = None,
    ) -> None:
        super().__init__(
            host=OUTLOOK_IMAP_HOST,
            port=OUTLOOK_IMAP_PORT,
            use_ssl=True,
            account_id=account_id,
        )
        self.email_address = email_address
        self.client_id = client_id
        self.authority = authority
        self._credential_store = credential_store or AccountCredentialStore()
        self._msal_app: msal.PublicClientApplication | None = None

    def _get_msal_app(self) -> msal.PublicClientApplication:
        """Get or create the MSAL application instance."""
        if self._msal_app is None:
            self._msal_app = msal.PublicClientApplication(
                client_id=self.client_id,
                authority=self.authority,
            )
        return self._msal_app

    async def authenticate(self, username: str = "", password: str = "") -> None:
        """Authenticate with Outlook using OAuth2 XOAUTH2.

        Tries silent token acquisition first, falls back to device flow.
        """
        client = self._ensure_client()
        access_token = await self._get_access_token()

        logger.info("Authenticating %s via XOAUTH2 (Outlook)", self.email_address)

        try:
            await self._run_sync(client.oauth2_login, self.email_address, access_token)
            logger.info("Outlook OAuth2 authentication successful for %s", self.email_address)
        except Exception as e:
            if "AUTHENTICATIONFAILED" in str(e):
                logger.warning("OAuth2 auth failed, forcing token refresh for %s", self.email_address)
                access_token = await self._refresh_token()
                await self._run_sync(client.oauth2_login, self.email_address, access_token)
                logger.info(
                    "Outlook OAuth2 re-authentication successful for %s", self.email_address
                )
            else:
                logger.exception("Outlook authentication failed for %s", self.email_address)
                raise

    async def _get_access_token(self) -> str:
        """Get a valid access token, using silent acquisition first."""
        # Try to get cached token
        tokens = self._credential_store.get_oauth_tokens(self.account_id)

        if tokens and tokens.get("access_token"):
            # Try silent token acquisition via MSAL
            app = self._get_msal_app()
            accounts = app.get_accounts(username=self.email_address)

            if accounts:
                result = await self._run_sync(
                    app.acquire_token_silent,
                    OUTLOOK_SCOPES,
                    account=accounts[0],
                )
                if result and "access_token" in result:
                    logger.debug("Silent token acquisition successful for %s", self.email_address)
                    # Update stored token
                    self._credential_store.store_oauth_tokens(
                        self.account_id,
                        {
                            "access_token": result["access_token"],
                            "refresh_token": tokens.get("refresh_token", ""),
                        },
                    )
                    return result["access_token"]

            # If silent fails but we have a cached token, try it
            if tokens.get("access_token"):
                return tokens["access_token"]

        raise ValueError(
            f"No valid OAuth tokens for Outlook account {self.account_id}. "
            "Run the device flow authorization first."
        )

    async def _refresh_token(self) -> str:
        """Force a token refresh via MSAL."""
        app = self._get_msal_app()
        accounts = app.get_accounts(username=self.email_address)

        if not accounts:
            raise ValueError(
                f"No MSAL accounts found for {self.email_address}. "
                "Re-run the device flow authorization."
            )

        result = await self._run_sync(
            app.acquire_token_silent,
            OUTLOOK_SCOPES,
            account=accounts[0],
            force_refresh=True,
        )

        if result and "access_token" in result:
            self._credential_store.store_oauth_tokens(
                self.account_id,
                {
                    "access_token": result["access_token"],
                    "refresh_token": result.get("refresh_token", ""),
                },
            )
            logger.info("Outlook token refreshed for %s", self.email_address)
            return result["access_token"]

        raise ValueError(f"Failed to refresh Outlook token for {self.email_address}")

    async def initiate_device_flow(self) -> dict:
        """Start the device flow authorization.

        Returns the flow dict containing 'user_code' and 'verification_uri'
        that the user needs to visit.
        """
        app = self._get_msal_app()
        flow = await self._run_sync(app.initiate_device_flow, scopes=OUTLOOK_SCOPES)

        if "user_code" not in flow:
            raise ValueError(f"Device flow initiation failed: {flow.get('error_description', '')}")

        logger.info(
            "Outlook device flow started for %s: visit %s and enter code %s",
            self.email_address,
            flow.get("verification_uri"),
            flow.get("user_code"),
        )
        return flow

    async def complete_device_flow(self, flow: dict) -> str:
        """Complete the device flow and store the obtained tokens.

        Args:
            flow: The flow dict from initiate_device_flow().

        Returns:
            The access token.
        """
        app = self._get_msal_app()
        result = await self._run_sync(app.acquire_token_by_device_flow, flow)

        if "access_token" not in result:
            raise ValueError(
                f"Device flow failed: {result.get('error_description', 'Unknown error')}"
            )

        # Store tokens
        self._credential_store.store_oauth_tokens(
            self.account_id,
            {
                "access_token": result["access_token"],
                "refresh_token": result.get("refresh_token", ""),
            },
        )

        logger.info("Outlook device flow completed for %s", self.email_address)
        return result["access_token"]
