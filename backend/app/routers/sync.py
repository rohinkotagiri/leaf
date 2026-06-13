"""Router for triggering and monitoring email synchronization and backfill."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services.storage.account_repo import AccountRepository
from app.workers.backfill import BackfillWorker, backfill_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])
account_repo = AccountRepository()


@router.get("/backfill-status", status_code=status.HTTP_200_OK)
async def get_backfill_status() -> dict[str, Any]:
    """Get the current progress of the historical analysis backfill."""
    return backfill_status.to_dict()


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
async def start_backfill(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Trigger the historical analysis backfill worker in the background."""
    if backfill_status.is_running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Backfill is already running",
        )

    worker = BackfillWorker()
    background_tasks.add_task(worker.run_backfill)
    return {"message": "Backfill started successfully"}


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_sync_status(session: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """Retrieve the current synchronization status/metrics for all accounts."""
    accounts = await account_repo.get_all(session)

    from app.workers.sync import SyncWorker

    status_list = []
    for account in accounts:
        status_list.append({
            "account_id": account.id,
            "email_address": account.email_address,
            "sync_enabled": account.sync_enabled,
            "is_running": account.id in SyncWorker._running_syncs,
            "is_idle_active": account.id in SyncWorker._idle_tasks,
            "last_sync_at": account.last_sync_at,
            "sync_cursor": account.sync_cursor,
        })
    return status_list


@router.post("/{account_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_account_sync(
    account_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Manually trigger synchronization for a specific account."""
    account = await account_repo.get_by_id(session, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    from app.workers.sync import SyncWorker
    worker = SyncWorker()
    background_tasks.add_task(worker.sync_account, account_id, True)
    return {"message": f"Synchronization triggered for account {account_id}"}
