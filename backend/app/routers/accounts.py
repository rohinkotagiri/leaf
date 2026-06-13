"""Router for managing email accounts and testing connections."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.account import ProviderType
from app.models.email import Email
from app.schemas.account import AccountCreate, AccountResponse
from app.services.imap import AccountCredentialStore, create_email_client
from app.services.storage.account_repo import AccountRepository
from app.services.storage.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
credential_store = AccountCredentialStore()
account_repo = AccountRepository()


class AccountCreateRequest(AccountCreate):
    """Extended creation schema allowing password or OAuth tokens to be securely supplied."""
    password: str | None = None
    oauth_tokens: dict | None = None


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    request: AccountCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """Register a new email account and securely store its credentials in the keyring."""
    # Check if account email already exists
    existing = await account_repo.get_by_email(session, request.email_address)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Account with email {request.email_address} already exists",
        )

    # Save to SQLite
    account = await account_repo.create(session, request)
    await session.commit()

    # Save credentials to keyring if provided
    try:
        if request.password:
            credential_store.store_password(account.id, request.password)
        if request.oauth_tokens:
            credential_store.store_oauth_tokens(account.id, request.oauth_tokens)
    except Exception as e:
        logger.error("Failed to store credentials for newly created account %s", account.id)
        # Roll back database entry to be consistent
        await account_repo.delete(session, account.id)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store account credentials securely: {str(e)}",
        ) from e

    # Start real-time sync if enabled
    if account.sync_enabled:
        try:
            from app.main import sync_worker
            await sync_worker.start_idle_loop(account.id)
        except Exception:
            logger.exception("Failed to start IDLE sync loop on account registration")

    return AccountResponse.model_validate(account)


@router.get("", response_model=list[AccountResponse], status_code=status.HTTP_200_OK)
async def list_accounts(session: AsyncSession = Depends(get_db)) -> list[AccountResponse]:
    """Retrieve list of all registered email accounts."""
    accounts = await account_repo.get_all(session)
    return [AccountResponse.model_validate(a) for a in accounts]


@router.delete("/{account_id}", status_code=status.HTTP_200_OK)
async def delete_account(
    account_id: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete account, clear keyring credentials, and cascade delete all emails, analyses, and embeddings."""
    account = await account_repo.get_by_id(session, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # 1. Stop any active sync loop
    try:
        from app.main import sync_worker
        await sync_worker.stop_idle_loop(account_id)
    except Exception:
        logger.warning("Failed to stop sync loop for account %s during deletion", account_id)

    # 2. Delete embeddings from ChromaDB
    try:
        stmt = select(Email.id).where(Email.account_id == account_id)
        res = await session.execute(stmt)
        email_ids = list(res.scalars().all())
        if email_ids:
            store = ChromaDBStore()
            await store.delete_by_ids(email_ids)
    except Exception:
        logger.exception("Failed to delete embeddings from ChromaDB for account %s", account_id)

    # 3. Clear keyring credentials
    try:
        credential_store.delete_credentials(account_id)
    except Exception:
        logger.warning("Failed to delete credentials from keyring for account %s", account_id)

    # 4. Delete account from database (cascade deletes emails, analyses via ForeignKey)
    await account_repo.delete(session, account_id)
    await session.commit()

    return {"message": "Account and all associated email and vector store data deleted successfully"}


@router.post("/{account_id}/test", status_code=status.HTTP_200_OK)
async def test_connection(
    account_id: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Verify connection and authentication parameters for the account."""
    account = await account_repo.get_by_id(session, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    client = create_email_client(account, credential_store)
    try:
        await client.connect()
        if account.provider == ProviderType.GENERIC:
            password = credential_store.get_password(account.id)
            if not password:
                raise ValueError("No password stored in keyring for this account")
            await client.authenticate(account.email_address, password)
        else:
            await client.authenticate()

        await client.disconnect()
        return {"success": True, "message": "Connection test successful"}
    except Exception as e:
        logger.warning("Connection test failed for account %s: %s", account.email_address, str(e))
        return {"success": False, "error": str(e)}
