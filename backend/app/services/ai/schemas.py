"""Pydantic result models returned by AI services."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MVP_CATEGORIES: tuple[str, ...] = (
    "work",
    "personal",
    "finance",
    "travel",
    "shopping",
    "newsletter",
    "notification",
    "security",
    "spam",
    "other",
)


class ClassificationResult(BaseModel):
    """Validated fast email classification result."""

    category: str
    priority_score: float = Field(ge=0.0, le=1.0)
    spam_score: float = Field(ge=0.0, le=1.0)
    is_phishing: bool
    suggested_action: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in MVP_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(MVP_CATEGORIES)}")
        return normalized


class ExtractedActionItem(BaseModel):
    """Task-like action extracted from an email."""

    task: str
    deadline: str | None = None
    priority: str | None = None


class Appointment(BaseModel):
    """Calendar-like appointment extracted from an email."""

    title: str = ""
    date: str | None = None
    time: str | None = None
    location: str | None = None
    attendees: list[str] = Field(default_factory=list)


class Commitment(BaseModel):
    """Promise made or requested in an email."""

    description: str
    owner: str | None = None
    due_date: str | None = None


class NamedEntities(BaseModel):
    """Named entities relevant to email workflows."""

    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    monetary_amounts: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Structured deep extraction result."""

    action_items: list[ExtractedActionItem] = Field(default_factory=list)
    appointments: list[Appointment] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    entities: NamedEntities = Field(default_factory=NamedEntities)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class URLSignal(BaseModel):
    """Risk signal for a URL found in an email body."""

    url: str
    domain: str
    risk_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class HeaderSignal(BaseModel):
    """Authentication-header risk signal."""

    spf_pass: bool | None = None
    dkim_pass: bool | None = None
    dmarc_pass: bool | None = None
    risk_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class LLMSpamSignal(BaseModel):
    """LLM phishing/spam judgment."""

    spam_score: float = Field(ge=0.0, le=1.0)
    is_phishing: bool
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class SpamDetectionResult(BaseModel):
    """Combined spam analysis from heuristic and LLM signals."""

    url_score: float = Field(ge=0.0, le=1.0)
    header_score: float = Field(ge=0.0, le=1.0)
    llm_score: float = Field(ge=0.0, le=1.0)
    combined_score: float = Field(ge=0.0, le=1.0)
    is_spam: bool
    is_phishing: bool
    confidence: float = Field(ge=0.0, le=1.0)
    urls: list[URLSignal] = Field(default_factory=list)
    header_signal: HeaderSignal
    llm_signal: LLMSpamSignal | None = None
