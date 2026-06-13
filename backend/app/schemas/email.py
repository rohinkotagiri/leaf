"""Pydantic schemas for email data — DTOs used across all layers."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class RecipientType(enum.StrEnum):
    """Type of email recipient."""

    TO = "to"
    CC = "cc"
    BCC = "bcc"


class Recipient(BaseModel):
    """A single email recipient."""

    name: str = ""
    email: str = ""
    type: RecipientType = RecipientType.TO


class Attachment(BaseModel):
    """Email attachment metadata (content is not stored)."""

    filename: str = ""
    content_type: str = ""
    size: int = 0


class EmailMessage(BaseModel):
    """Core email DTO — the application-level representation of an email.

    This is the primary data structure passed between parser, storage,
    AI services, and API responses. It is NOT the ORM model.
    """

    id: str = ""
    account_id: str = ""
    thread_id: str = ""
    message_id: str = ""
    subject: str = ""
    sender_name: str = ""
    sender_email: str = ""
    recipients: list[Recipient] = Field(default_factory=list)
    date: datetime | None = None
    body_text: str = ""
    body_html: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    raw_headers: dict[str, str] = Field(default_factory=dict)
    folder: str = "INBOX"
    flags: list[str] = Field(default_factory=list)
    uid: int = 0
    in_reply_to: str = ""
    references: list[str] = Field(default_factory=list)


class EmailResponse(BaseModel):
    """API response for a single email."""

    id: str
    account_id: str
    thread_id: str
    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    recipients: list[Recipient]
    date: datetime | None
    body_text: str
    folder: str
    flags: list[str]
    attachments: list[Attachment]
    has_html: bool = False


class EmailListResponse(BaseModel):
    """API response for a list of emails."""

    emails: list[EmailResponse]
    total: int
    offset: int = 0
    limit: int = 50
