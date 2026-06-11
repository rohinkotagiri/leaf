"""Pydantic schemas — public exports."""

from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from app.schemas.email import (
    Attachment,
    EmailListResponse,
    EmailMessage,
    EmailResponse,
    Recipient,
    RecipientType,
)

__all__ = [
    "AccountCreate",
    "AccountResponse",
    "AccountUpdate",
    "Attachment",
    "EmailListResponse",
    "EmailMessage",
    "EmailResponse",
    "Recipient",
    "RecipientType",
]
