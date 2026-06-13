"""Email account ORM model."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.email import Email
    from app.models.thread import Thread


class ProviderType(str, enum.Enum):
    """Supported email provider types."""

    GMAIL = "gmail"
    OUTLOOK = "outlook"
    GENERIC = "generic"


class Account(Base):
    """Email account connected via IMAP."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email_address: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider: Mapped[ProviderType] = mapped_column(
        Enum(ProviderType), default=ProviderType.GENERIC, nullable=False
    )
    credentials_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    imap_host: Mapped[str] = mapped_column(String(255), default="")
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_cursor: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    emails: Mapped[list[Email]] = relationship(
        "Email", back_populates="account", cascade="all, delete-orphan"
    )
    threads: Mapped[list[Thread]] = relationship(
        "Thread", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Account {self.email_address} ({self.provider.value})>"
