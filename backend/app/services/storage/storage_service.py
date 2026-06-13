"""Storage service — coordinates SQL and vector store operations.

Ensures emails are saved to both SQLite (metadata + content) and
ChromaDB (embeddings) atomically where possible, with graceful
degradation if ChromaDB is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.email import EmailMessage
from app.services.storage.email_repo import EmailRepository
from app.services.storage.vector_store import ChromaDBStore

logger = logging.getLogger(__name__)


class StorageService:
    """Coordinates between SQL repositories and the vector store.

    Handles partial failures: if ChromaDB is down, SQL saves still
    succeed and the email is marked is_indexed=False for later retry.
    """

    def __init__(
        self,
        email_repo: EmailRepository | None = None,
        vector_store: ChromaDBStore | None = None,
    ) -> None:
        self._email_repo = email_repo or EmailRepository()
        self._vector_store = vector_store

    @property
    def email_repo(self) -> EmailRepository:
        return self._email_repo

    @property
    def vector_store(self) -> ChromaDBStore | None:
        return self._vector_store

    async def ingest_email(
        self,
        session: AsyncSession,
        email_msg: EmailMessage,
        *,
        embedding: list[float] | None = None,
        raw_size_bytes: int | None = None,
    ) -> str:
        """Ingest a single email: save to SQL and optionally add embedding.

        Args:
            session: Database session.
            email_msg: Parsed email DTO.
            embedding: Pre-computed embedding vector (optional).
            raw_size_bytes: Size of the raw email in bytes.

        Returns:
            The saved email's ID.
        """
        # Save to SQL first (this is the authoritative store)
        email = await self._email_repo.save_email(
            session, email_msg, raw_size_bytes=raw_size_bytes
        )

        # Optionally add embedding to vector store
        if embedding is not None and self._vector_store is not None:
            try:
                metadata = self._build_vector_metadata(email_msg)
                await self._vector_store.add_embedding(
                    email_id=email.id,
                    embedding=embedding,
                    metadata=metadata,
                )
                await self._email_repo.mark_indexed(session, email.id)
            except Exception:
                logger.warning(
                    "Failed to add embedding for email %s — will retry later",
                    email.id[:12],
                    exc_info=True,
                )

        return email.id

    async def ingest_emails_bulk(
        self,
        session: AsyncSession,
        email_msgs: list[EmailMessage],
        *,
        embeddings: dict[str, list[float]] | None = None,
    ) -> int:
        """Bulk ingest emails into SQL, optionally with embeddings.

        Args:
            session: Database session.
            email_msgs: List of parsed email DTOs.
            embeddings: Optional mapping of email_id → embedding vector.

        Returns:
            Number of emails inserted into SQL.
        """
        # Bulk insert into SQL
        count = await self._email_repo.save_emails_bulk(session, email_msgs)

        # Add embeddings to vector store if provided
        if embeddings and self._vector_store is not None:
            items: list[dict[str, Any]] = []
            for msg in email_msgs:
                if msg.id in embeddings:
                    items.append(
                        {
                            "id": msg.id,
                            "embedding": embeddings[msg.id],
                            "metadata": self._build_vector_metadata(msg),
                        }
                    )

            if items:
                try:
                    await self._vector_store.add_embeddings_bulk(items)
                    # Mark indexed
                    for item in items:
                        await self._email_repo.mark_indexed(session, item["id"])
                except Exception:
                    logger.warning(
                        "Failed to bulk add %d embeddings — will retry later",
                        len(items),
                        exc_info=True,
                    )

        return count

    async def delete_email(
        self,
        session: AsyncSession,
        email_id: str,
    ) -> bool:
        """Delete an email from both SQL and vector store.

        Returns:
            True if the email existed in SQL and was deleted.
        """
        email = await self._email_repo.get_by_id(session, email_id)
        if email is None:
            return False

        # Delete from vector store first (non-critical)
        if self._vector_store is not None:
            try:
                await self._vector_store.delete_by_id(email_id)
            except Exception:
                logger.warning(
                    "Failed to delete embedding for email %s", email_id[:12]
                )

        # Delete from SQL (cascade will remove analysis + feedback)
        await session.delete(email)
        await session.flush()

        logger.debug("Deleted email %s from all stores", email_id[:12])
        return True

    @staticmethod
    def _build_vector_metadata(email_msg: EmailMessage) -> dict[str, Any]:
        """Build lightweight metadata for ChromaDB storage.

        Only includes small, filterable fields — never the full body.
        """
        meta: dict[str, Any] = {
            "account_id": email_msg.account_id,
            "folder": email_msg.folder,
            "sender_email": email_msg.sender_email,
            "has_attachments": len(email_msg.attachments) > 0,
        }
        if email_msg.date:
            meta["date_iso"] = email_msg.date.isoformat()
        if email_msg.subject:
            meta["subject_short"] = email_msg.subject[:100]
        return meta
