"""Background worker for historical email analysis backfill."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import func, select

from app.database import async_session_factory
from app.models.email import Email
from app.services.pipeline import AnalysisPipeline

logger = logging.getLogger(__name__)


class BackfillStatus:
    """Thread-safe state tracker for historical backfill operations."""

    def __init__(self) -> None:
        self.is_running = False
        self.total = 0
        self.completed = 0
        self.failed = 0
        self.start_time: float | None = None

    def reset(self, total: int) -> None:
        """Reset progress stats and start the timer."""
        self.is_running = True
        self.total = total
        self.completed = 0
        self.failed = 0
        self.start_time = time.perf_counter()

    def stop(self) -> None:
        """Stop tracking backfill execution."""
        self.is_running = False

    def to_dict(self) -> dict[str, Any]:
        """Convert current status to a dictionary with runtime stats and ETA."""
        if not self.is_running:
            return {
                "is_running": False,
                "total": self.total,
                "completed": self.completed,
                "failed": self.failed,
                "elapsed_seconds": 0.0,
                "eta_seconds": 0.0,
            }

        elapsed = time.perf_counter() - self.start_time if self.start_time else 0.0
        processed = self.completed + self.failed

        if processed > 0:
            rate = processed / elapsed
            remaining = self.total - processed
            eta = remaining / rate if rate > 0 else 0.0
        else:
            eta = 0.0

        return {
            "is_running": True,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": round(max(0.0, eta), 1),
        }


# Singleton backfill progress tracker
backfill_status = BackfillStatus()


class BackfillWorker:
    """Manages bulk asynchronous backfill processing for all unanalyzed emails."""

    def __init__(self, pipeline: AnalysisPipeline | None = None) -> None:
        self.pipeline = pipeline or AnalysisPipeline()
        self._lock = asyncio.Lock()

    async def run_backfill(self) -> None:
        """Query all unanalyzed emails and process them in batches of 10 using a semaphore."""
        async with self._lock:
            if backfill_status.is_running:
                logger.warning("Backfill is already in progress. Skipping execution.")
                return

            async with async_session_factory() as session:
                stmt = select(func.count(Email.id)).where(Email.is_analyzed == False)  # noqa: E712
                res = await session.execute(stmt)
                total_unanalyzed = res.scalar() or 0

                if total_unanalyzed == 0:
                    logger.info("No unanalyzed emails found. Backfill unnecessary.")
                    return

                backfill_status.reset(total_unanalyzed)

        logger.info("Starting email analysis backfill for %d emails", total_unanalyzed)

        try:
            # Retrieve all unanalyzed email IDs
            async with async_session_factory() as session:
                stmt = select(Email.id).where(Email.is_analyzed == False).order_by(Email.date.desc())  # noqa: E712
                res = await session.execute(stmt)
                email_ids = list(res.scalars().all())

            # Process emails concurrently using a semaphore to limit parallelism to 10
            sem = asyncio.Semaphore(10)

            async def process_one(email_id: str) -> None:
                async with sem:
                    # Each task must use its own distinct session to avoid sharing session transactions
                    async with async_session_factory() as task_session:
                        try:
                            # analyze_email handles internal saving and websocket notification
                            res = await self.pipeline.analyze_email(task_session, email_id)
                            if res.success:
                                await task_session.commit()
                                backfill_status.completed += 1
                            else:
                                await task_session.rollback()
                                backfill_status.failed += 1
                                logger.error("Failed to analyze email %s: %s", email_id, res.errors)
                        except Exception:
                            await task_session.rollback()
                            backfill_status.failed += 1
                            logger.exception("Unexpected error analyzing email %s during backfill", email_id)

            # Schedule and await all tasks
            tasks = [process_one(eid) for eid in email_ids]
            await asyncio.gather(*tasks)

        finally:
            backfill_status.stop()
            logger.info("Backfill complete. Completed: %d, Failed: %d", backfill_status.completed, backfill_status.failed)
