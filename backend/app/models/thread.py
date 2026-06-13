"""Thread ORM model — groups related emails into conversation threads."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.email import Email


class Thread(Base):
    """Conversation thread grouping related emails."""

    __tablename__ = "threads"
    __table_args__ = (
        Index("idx_threads_account", "account_id"),
        Index("idx_threads_last_activity", "last_activity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    subject_base: Mapped[str] = mapped_column(
        String(500), nullable=False, default=""
    )
    participants_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_activity: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    account: Mapped[Account] = relationship("Account", back_populates="threads")
    emails: Mapped[list[Email]] = relationship(
        "Email", back_populates="thread", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Thread {self.id[:8]}... ({self.message_count} msgs)>"
