"""FastAPI application entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import async_session_factory
from app.models.account import Account
from app.routers.websocket import router as websocket_router
from app.routers.sync import router as sync_router
from app.workers.sync import SyncWorker
from sqlalchemy import select

logger = logging.getLogger(__name__)

sync_worker = SyncWorker()


async def periodic_sync_task() -> None:
    """Trigger email sync periodically based on configured sync interval."""
    # Sleep on startup to allow services to initialize
    await asyncio.sleep(10)
    while True:
        try:
            logger.info("Executing scheduled periodic sync for all accounts")
            await sync_worker.sync_all_accounts()
        except Exception:
            logger.exception("Scheduled periodic sync execution failed")
        
        # Sleep until next sync interval
        interval_seconds = settings.SYNC_INTERVAL_MINUTES * 60
        await asyncio.sleep(interval_seconds)


async def start_all_idle_tasks() -> None:
    """Fetch all active accounts and launch their IMAP IDLE connections."""
    try:
        async with async_session_factory() as session:
            stmt = select(Account).where(Account.sync_enabled == True)  # noqa: E712
            res = await session.execute(stmt)
            accounts = list(res.scalars().all())

        for account in accounts:
            await sync_worker.start_idle_loop(account.id)
    except Exception:
        logger.exception("Failed to launch startup IMAP IDLE listeners")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle."""
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    
    # Startup tasks
    periodic_task = asyncio.create_task(periodic_sync_task())
    idle_task = asyncio.create_task(start_all_idle_tasks())

    yield
    
    # Shutdown tasks
    logger.info("Shutting down workers and connections...")
    periodic_task.cancel()
    idle_task.cancel()
    await sync_worker.stop_all_idle_loops()
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Privacy-first local AI email assistant",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register endpoints
app.include_router(websocket_router)
app.include_router(sync_router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "version": settings.APP_VERSION}
