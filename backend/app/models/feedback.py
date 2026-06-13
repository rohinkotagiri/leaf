"""UserFeedback ORM model — captures user corrections to AI analysis."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.email import Email


class UserFeedback(Base):
    """Record of a user correction to an AI-generated field.

    Used to improve AI prompts over time by tracking which predictions
    users disagree with and what the correct values should be.
    """

    __tablename__ = "user_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    email: Mapped[Email] = relationship("Email")

    def __repr__(self) -> str:
        return (
            f"<UserFeedback #{self.id} email={self.email_id[:12]}... "
            f"field={self.field}>"
        )
