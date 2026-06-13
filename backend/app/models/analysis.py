"""EmailAnalysis ORM model — stores AI analysis results for an email."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.email import Email


class EmailAnalysis(Base):
    """AI-generated analysis of a single email.

    One-to-one relationship with Email. Stores classification, summary,
    extracted information, and model provenance for reproducibility.
    """

    __tablename__ = "email_analyses"

    email_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("emails.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    spam_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_phishing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    extracted_dates: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    extracted_entities: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    suggested_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    email: Mapped[Email] = relationship("Email", back_populates="analysis")

    def __repr__(self) -> str:
        return (
            f"<EmailAnalysis email={self.email_id[:12]}... "
            f"category={self.category} priority={self.priority_score}>"
        )
