"""Storage service — public API for data access.

Provides repository classes and the coordinating StorageService.
"""

from app.services.storage.account_repo import AccountRepository
from app.services.storage.analysis_repo import AnalysisRepository
from app.services.storage.email_repo import EmailRepository
from app.services.storage.storage_service import StorageService
from app.services.storage.vector_store import ChromaDBStore

__all__ = [
    "AccountRepository",
    "AnalysisRepository",
    "ChromaDBStore",
    "EmailRepository",
    "StorageService",
]
