"""Credential store — manages OAuth tokens and passwords via keyring.

All credentials are stored securely through the system keyring.
Never stores credentials in .env, database, or filesystem.
"""

from __future__ import annotations

import json
import logging

import keyring

logger = logging.getLogger(__name__)

SERVICE_NAME = "privatemailai"


class AccountCredentialStore:
    """Store and retrieve account credentials via the system keyring."""

    def store_oauth_tokens(self, account_id: str, tokens: dict) -> None:
        """Store OAuth2 tokens (access_token, refresh_token, etc.) for an account.

        Args:
            account_id: The account ID to store tokens for.
            tokens: Dict containing at minimum 'access_token' and optionally
                'refresh_token', 'token_uri', 'client_id', 'client_secret', 'expiry'.
        """
        key = f"oauth:{account_id}"
        try:
            keyring.set_password(SERVICE_NAME, key, json.dumps(tokens))
            logger.info("Stored OAuth tokens for account %s", account_id)
        except Exception:
            logger.exception("Failed to store OAuth tokens for account %s", account_id)
            raise

    def get_oauth_tokens(self, account_id: str) -> dict | None:
        """Retrieve OAuth2 tokens for an account.

        Returns:
            Token dict if found, None otherwise.
        """
        key = f"oauth:{account_id}"
        try:
            data = keyring.get_password(SERVICE_NAME, key)
            if data is None:
                return None
            return json.loads(data)
        except json.JSONDecodeError:
            logger.error("Corrupted OAuth token data for account %s", account_id)
            return None
        except Exception:
            logger.exception("Failed to retrieve OAuth tokens for account %s", account_id)
            return None

    def store_password(self, account_id: str, password: str) -> None:
        """Store an IMAP password for an account.

        Args:
            account_id: The account ID.
            password: The IMAP password or app-specific password.
        """
        key = f"password:{account_id}"
        try:
            keyring.set_password(SERVICE_NAME, key, password)
            logger.info("Stored password for account %s", account_id)
        except Exception:
            logger.exception("Failed to store password for account %s", account_id)
            raise

    def get_password(self, account_id: str) -> str | None:
        """Retrieve an IMAP password for an account.

        Returns:
            The password string if found, None otherwise.
        """
        key = f"password:{account_id}"
        try:
            return keyring.get_password(SERVICE_NAME, key)
        except Exception:
            logger.exception("Failed to retrieve password for account %s", account_id)
            return None

    def delete_credentials(self, account_id: str) -> None:
        """Delete all stored credentials for an account.

        Removes both OAuth tokens and passwords.
        """
        for prefix in ("oauth", "password"):
            key = f"{prefix}:{account_id}"
            try:
                keyring.delete_password(SERVICE_NAME, key)
                logger.info("Deleted %s credentials for account %s", prefix, account_id)
            except keyring.errors.PasswordDeleteError:
                # Key didn't exist — that's fine
                pass
            except Exception:
                logger.warning(
                    "Failed to delete %s credentials for account %s", prefix, account_id
                )
