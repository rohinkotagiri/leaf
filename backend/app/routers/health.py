"""Router for application health checking."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services.ai.client import OllamaClient
from app.services.storage.vector_store import ChromaDBStore
from app.workers.sync import SyncWorker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", status_code=status.HTTP_200_OK)
async def health_check(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Check availability of SQLite DB, ChromaDB Vector Store, Ollama, and Sync loops."""
    # 1. DB check
    db_healthy = False
    db_error = None
    try:
        await session.execute(text("SELECT 1"))
        db_healthy = True
    except Exception as e:
        db_error = str(e)
        logger.error("Health check database error: %s", db_error)

    # 2. ChromaDB check
    chroma_healthy = False
    chroma_count = 0
    chroma_error = None
    try:
        store = ChromaDBStore()
        stats = await store.get_collection_stats()
        chroma_count = stats.get("count", 0)
        chroma_healthy = True
    except Exception as e:
        chroma_error = str(e)
        logger.error("Health check ChromaDB error: %s", chroma_error)

    # 3. Ollama check
    ollama_healthy = False
    ollama_error = None
    try:
        # Avoid import errors, use try/except
        try:
            client = OllamaClient()
            ollama_healthy = await client.is_running()
            if not ollama_healthy:
                ollama_error = "Ollama client reports not running"
        except Exception as client_err:
            ollama_error = str(client_err)
    except Exception as e:
        ollama_error = str(e)
        logger.error("Health check Ollama error: %s", ollama_error)

    # 4. Sync status
    active_idle_connections = len(SyncWorker._idle_tasks)

    overall_healthy = db_healthy and chroma_healthy and ollama_healthy

    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "database": {
            "healthy": db_healthy,
            "error": db_error,
        },
        "chromadb": {
            "healthy": chroma_healthy,
            "count": chroma_count,
            "error": chroma_error,
        },
        "ollama": {
            "healthy": ollama_healthy,
            "error": ollama_error,
        },
        "sync": {
            "active_idle_connections": active_idle_connections,
        },
    }
