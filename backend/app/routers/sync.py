"""Router for triggering and monitoring email synchronization and backfill."""

from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.workers.backfill import backfill_status, BackfillWorker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/backfill-status", status_code=status.HTTP_200_OK)
async def get_backfill_status() -> dict:
    """Get the current progress of the historical analysis backfill."""
    return backfill_status.to_dict()


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
async def start_backfill(background_tasks: BackgroundTasks) -> dict:
    """Trigger the historical analysis backfill worker in the background."""
    if backfill_status.is_running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Backfill is already running",
        )
    
    worker = BackfillWorker()
    background_tasks.add_task(worker.run_backfill)
    return {"message": "Backfill started successfully"}


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(background_tasks: BackgroundTasks) -> dict:
    """Manually trigger synchronization for all active accounts."""
    # We will import SyncWorker and trigger sync in background
    from app.workers.sync import SyncWorker
    worker = SyncWorker()
    background_tasks.add_task(worker.sync_all_accounts)
    return {"message": "Manual synchronization triggered"}
