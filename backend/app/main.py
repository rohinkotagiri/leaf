"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import async_session_factory
from app.models.account import Account
from app.routers.accounts import router as accounts_router
from app.routers.emails import router as emails_router
from app.routers.feedback import router as feedback_router
from app.routers.health import router as health_router
from app.routers.search import router as search_router
from app.routers.sync import router as sync_router
from app.routers.websocket import router as websocket_router
from app.workers.sync import SyncWorker

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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request details and execution latencies."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info(
                "API Request: %s %s - Status: %s - Duration: %.2fms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(
                "API Request Failed: %s %s - Duration: %.2fms - Error: %s",
                request.method,
                request.url.path,
                duration_ms,
                str(exc),
                exc_info=True,
            )
            raise


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

# Request response logging middleware
app.add_middleware(RequestLoggingMiddleware)

# CORS — restrict strictly to localhost origins
localhost_origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=localhost_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handlers
@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Global handler for database unique constraint or foreign key check violations."""
    logger.error("DB Constraint error on %s: %s", request.url.path, str(exc))
    return JSONResponse(
        status_code=400,
        content={"detail": "Database integrity constraint violation. Please verify input data uniqueness."},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled errors returning standard 500 status."""
    logger.exception("Unhandled error during processing %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again later."},
    )


# Register endpoints
app.include_router(websocket_router)
app.include_router(sync_router)
app.include_router(health_router)
app.include_router(accounts_router)
app.include_router(emails_router)
app.include_router(search_router)
app.include_router(feedback_router)
