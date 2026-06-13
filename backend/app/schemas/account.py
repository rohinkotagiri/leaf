"""Pydantic schemas for email account management."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.account import ProviderType


class AccountCreate(BaseModel):
    """Schema for creating a new email account."""

    email_address: EmailStr
    display_name: str = ""
    provider: ProviderType = ProviderType.GENERIC
    imap_host: str = ""
    imap_port: int = 993
    use_ssl: bool = True
    credentials_key: str | None = None


class AccountUpdate(BaseModel):
    """Schema for updating an existing email account."""

    display_name: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    use_ssl: bool | None = None
    sync_enabled: bool | None = None
    credentials_key: str | None = None


class AccountResponse(BaseModel):
    """API response for an email account."""

    id: str
    email_address: str
    display_name: str
    provider: ProviderType
    imap_host: str
    imap_port: int
    use_ssl: bool
    sync_enabled: bool
    credentials_key: str | None
    last_sync_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
