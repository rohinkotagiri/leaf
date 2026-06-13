"""Email ORM model — represents a single email message stored locally."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.analysis import EmailAnalysis
    from app.models.thread import Thread


class Email(Base):
    """A single email message with parsed content."""

    __tablename__ = "emails"
    __table_args__ = (
        Index("idx_emails_account", "account_id"),
        Index("idx_emails_thread", "thread_id"),
        Index("idx_emails_date", "date"),
        Index("idx_emails_analyzed", "is_analyzed"),
        Index("idx_emails_indexed", "is_indexed"),
        Index("idx_emails_sender", "sender_email"),
        Index("idx_emails_folder", "account_id", "folder"),
    )

    # PK: sha256(account_id + uid + folder) — ensures uniqueness across accounts
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    thread_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("threads.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    uid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    folder: Mapped[str] = mapped_column(String(255), nullable=False, default="INBOX")

    # Content
    subject: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    recipients_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_html: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Attachment metadata
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attachment_names: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Flags & labels
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_important: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    labels: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Processing state
    is_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_analyzed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Threading headers (for reconstruction)
    in_reply_to: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    references_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    raw_headers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Size
    raw_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    account: Mapped[Account] = relationship("Account", back_populates="emails")
    thread: Mapped[Thread | None] = relationship("Thread", back_populates="emails")
    analysis: Mapped[EmailAnalysis | None] = relationship(
        "EmailAnalysis", back_populates="email", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Email {self.id[:12]}... '{self.subject[:30]}'>"
