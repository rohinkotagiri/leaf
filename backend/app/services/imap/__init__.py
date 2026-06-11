"""IMAP email service — public API for email connectivity.

Provides a factory function to create the correct email client
based on the account's provider type.
"""

from __future__ import annotations

from app.models.account import Account, ProviderType
from app.services.imap.client import BaseEmailClient, ImapClient
from app.services.imap.credential_store import AccountCredentialStore
from app.services.imap.gmail import GmailClient
from app.services.imap.outlook import OutlookClient
from app.services.imap.parser import EmailParser
from app.services.imap.pool import ConnectionPool
from app.services.imap.threading import ThreadReconstructor

__all__ = [
    "AccountCredentialStore",
    "BaseEmailClient",
    "ConnectionPool",
    "EmailParser",
    "GmailClient",
    "ImapClient",
    "OutlookClient",
    "ThreadReconstructor",
    "create_email_client",
]


def create_email_client(
    account: Account,
    credential_store: AccountCredentialStore | None = None,
) -> BaseEmailClient:
    """Factory function — create the correct email client for an account.

    Args:
        account: The Account ORM instance with provider and connection details.
        credential_store: Optional credential store (creates a default if not provided).

    Returns:
        A configured BaseEmailClient subclass ready to connect().
    """
    store = credential_store or AccountCredentialStore()

    if account.provider == ProviderType.GMAIL:
        return GmailClient(
            account_id=account.id,
            email_address=account.email_address,
            credential_store=store,
        )

    if account.provider == ProviderType.OUTLOOK:
        return OutlookClient(
            account_id=account.id,
            email_address=account.email_address,
            credential_store=store,
        )

    # Generic IMAP
    return ImapClient(
        host=account.imap_host,
        port=account.imap_port,
        use_ssl=account.use_ssl,
        account_id=account.id,
    )
