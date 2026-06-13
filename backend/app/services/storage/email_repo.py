"""Email repository — async CRUD operations for the Email model.

Provides a clean data-access layer so business logic never touches
SQLAlchemy directly. All methods accept an AsyncSession.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email import Email
from app.schemas.email import Attachment, EmailMessage, Recipient

logger = logging.getLogger(__name__)


class EmailRepository:
    """Async repository for Email CRUD operations."""

    # ── Write operations ──────────────────────────────────────────────

    async def save_email(
        self,
        session: AsyncSession,
        email_msg: EmailMessage,
        *,
        raw_size_bytes: int | None = None,
    ) -> Email:
        """Save a parsed EmailMessage to the database (upsert by PK).

        Converts the Pydantic EmailMessage DTO into an ORM Email instance.
        If an email with the same ID already exists, it is updated.

        Returns:
            The saved/updated Email ORM instance.
        """
        email = await self.get_by_id(session, email_msg.id)

        if email is None:
            email = Email(id=email_msg.id)
            session.add(email)

        # Map fields from DTO → ORM
        email.account_id = email_msg.account_id
        email.message_id = email_msg.message_id
        email.uid = email_msg.uid
        email.folder = email_msg.folder
        email.subject = email_msg.subject
        email.sender_name = email_msg.sender_name
        email.sender_email = email_msg.sender_email
        email.recipients_json = json.dumps(
            [r.model_dump() for r in email_msg.recipients]
        )
        email.date = email_msg.date
        email.body_text = email_msg.body_text
        email.body_html = email_msg.body_html
        email.has_attachments = len(email_msg.attachments) > 0
        email.attachment_names = json.dumps(
            [a.filename for a in email_msg.attachments if a.filename]
        )
        email.is_read = "\\Seen" in email_msg.flags
        email.is_starred = "\\Flagged" in email_msg.flags
        email.in_reply_to = email_msg.in_reply_to
        email.references_json = json.dumps(email_msg.references)
        email.raw_headers_json = json.dumps(email_msg.raw_headers)
        email.raw_size_bytes = raw_size_bytes
        email.thread_id = email_msg.thread_id or None

        await session.flush()

        logger.debug("Saved email %s (subject='%s')", email.id[:12], email.subject[:40])
        return email

    async def save_emails_bulk(
        self,
        session: AsyncSession,
        email_msgs: list[EmailMessage],
    ) -> int:
        """Bulk insert emails, skipping duplicates (ON CONFLICT DO NOTHING).

        Returns:
            Number of emails actually inserted.
        """
        if not email_msgs:
            return 0

        values = []
        for msg in email_msgs:
            values.append(
                {
                    "id": msg.id,
                    "account_id": msg.account_id,
                    "message_id": msg.message_id,
                    "uid": msg.uid,
                    "folder": msg.folder,
                    "subject": msg.subject,
                    "sender_name": msg.sender_name,
                    "sender_email": msg.sender_email,
                    "recipients_json": json.dumps(
                        [r.model_dump() for r in msg.recipients]
                    ),
                    "date": msg.date,
                    "body_text": msg.body_text,
                    "body_html": msg.body_html,
                    "has_attachments": len(msg.attachments) > 0,
                    "attachment_names": json.dumps(
                        [a.filename for a in msg.attachments if a.filename]
                    ),
                    "is_read": "\\Seen" in msg.flags,
                    "is_starred": "\\Flagged" in msg.flags,
                    "in_reply_to": msg.in_reply_to,
                    "references_json": json.dumps(msg.references),
                    "raw_headers_json": json.dumps(msg.raw_headers),
                    "thread_id": msg.thread_id or None,
                }
            )

        stmt = sqlite_upsert(Email).values(values).on_conflict_do_nothing(index_elements=["id"])
        result = await session.execute(stmt)
        await session.flush()

        rowcount = getattr(result, "rowcount", -1)
        inserted = rowcount if rowcount >= 0 else len(values)
        logger.info("Bulk inserted %d/%d emails", inserted, len(values))
        return inserted

    # ── Read operations ───────────────────────────────────────────────

    async def get_by_id(self, session: AsyncSession, email_id: str) -> Email | None:
        """Get a single email by its ID."""
        return await session.get(Email, email_id)

    async def get_by_thread(
        self,
        session: AsyncSession,
        thread_id: str,
    ) -> list[Email]:
        """Get all emails belonging to a thread, ordered by date."""
        stmt = (
            select(Email)
            .where(Email.thread_id == thread_id)
            .order_by(Email.date.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_paginated(
        self,
        session: AsyncSession,
        *,
        account_id: str | None = None,
        folder: str | None = None,
        is_read: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Email], int]:
        """Get paginated emails with optional filters.

        Returns:
            Tuple of (emails, total_count).
        """
        base = select(Email)
        count_base = select(func.count(Email.id))

        if account_id:
            base = base.where(Email.account_id == account_id)
            count_base = count_base.where(Email.account_id == account_id)
        if folder:
            base = base.where(Email.folder == folder)
            count_base = count_base.where(Email.folder == folder)
        if is_read is not None:
            base = base.where(Email.is_read == is_read)
            count_base = count_base.where(Email.is_read == is_read)

        # Get total count
        total_result = await session.execute(count_base)
        total = total_result.scalar() or 0

        # Get page
        stmt = base.order_by(Email.date.desc()).offset(offset).limit(limit)
        result = await session.execute(stmt)
        emails = list(result.scalars().all())

        return emails, total

    # ── Update operations ─────────────────────────────────────────────

    async def mark_read(
        self, session: AsyncSession, email_id: str, is_read: bool = True
    ) -> None:
        """Mark an email as read or unread."""
        email = await session.get(Email, email_id)
        if email:
            email.is_read = is_read
            await session.flush()

    async def update_labels(
        self, session: AsyncSession, email_id: str, labels: list[str]
    ) -> None:
        """Update the labels for an email."""
        email = await session.get(Email, email_id)
        if email:
            email.labels = json.dumps(labels)
            await session.flush()

    async def mark_analyzed(self, session: AsyncSession, email_id: str) -> None:
        """Mark an email as having been analyzed by AI."""
        email = await session.get(Email, email_id)
        if email:
            email.is_analyzed = True
            await session.flush()

    async def mark_indexed(self, session: AsyncSession, email_id: str) -> None:
        """Mark an email as having its embedding stored in the vector store."""
        email = await session.get(Email, email_id)
        if email:
            email.is_indexed = True
            await session.flush()

    # ── Query operations ──────────────────────────────────────────────

    async def get_unanalyzed(
        self, session: AsyncSession, limit: int = 50
    ) -> list[Email]:
        """Get emails that haven't been analyzed yet."""
        stmt = (
            select(Email)
            .where(Email.is_analyzed == False)  # noqa: E712
            .order_by(Email.date.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_unindexed(
        self, session: AsyncSession, limit: int = 50
    ) -> list[Email]:
        """Get emails that don't have embeddings stored yet."""
        stmt = (
            select(Email)
            .where(Email.is_indexed == False)  # noqa: E712
            .order_by(Email.date.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def search_by_metadata(
        self,
        session: AsyncSession,
        *,
        account_id: str | None = None,
        sender: str | None = None,
        subject_contains: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        folder: str | None = None,
        has_attachments: bool | None = None,
        limit: int = 50,
    ) -> list[Email]:
        """Search emails by metadata filters."""
        stmt = select(Email)

        if account_id:
            stmt = stmt.where(Email.account_id == account_id)
        if sender:
            stmt = stmt.where(Email.sender_email.ilike(f"%{sender}%"))
        if subject_contains:
            stmt = stmt.where(Email.subject.ilike(f"%{subject_contains}%"))
        if date_from:
            stmt = stmt.where(Email.date >= date_from)
        if date_to:
            stmt = stmt.where(Email.date <= date_to)
        if folder:
            stmt = stmt.where(Email.folder == folder)
        if has_attachments is not None:
            stmt = stmt.where(Email.has_attachments == has_attachments)

        stmt = stmt.order_by(Email.date.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_account(
        self, session: AsyncSession, account_id: str
    ) -> int:
        """Count emails for an account."""
        stmt = select(func.count(Email.id)).where(Email.account_id == account_id)
        result = await session.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    def email_to_message(email: Email) -> EmailMessage:
        """Convert an Email ORM instance back to an EmailMessage DTO."""
        return EmailMessage(
            id=email.id,
            account_id=email.account_id,
            thread_id=email.thread_id or "",
            message_id=email.message_id,
            subject=email.subject,
            sender_name=email.sender_name,
            sender_email=email.sender_email,
            recipients=[
                Recipient(**r) for r in json.loads(email.recipients_json)
            ],
            date=email.date,
            body_text=email.body_text,
            body_html=email.body_html,
            attachments=[
                Attachment(filename=name)
                for name in json.loads(email.attachment_names)
            ],
            raw_headers=json.loads(email.raw_headers_json),
            folder=email.folder,
            uid=email.uid,
            in_reply_to=email.in_reply_to,
            references=json.loads(email.references_json),
        )
