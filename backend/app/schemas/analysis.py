"""Pydantic schemas for AI email analysis."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ActionItem(BaseModel):
    """An extracted action item from an email."""

    task: str
    deadline: str | None = None
    priority: str | None = None


class ExtractedDate(BaseModel):
    """A date reference extracted from email content."""

    date: str
    context: str = ""


class AnalysisCreate(BaseModel):
    """Schema for creating a new analysis record."""

    email_id: str
    is_pending: bool = True
    category: str | None = None
    priority_score: float | None = None
    spam_score: float | None = None
    is_phishing: bool = False
    summary: str | None = None
    action_items: list[ActionItem] = Field(default_factory=list)
    extracted_dates: list[ExtractedDate] = Field(default_factory=list)
    extracted_entities: dict[str, list[str]] = Field(default_factory=dict)
    suggested_action: str | None = None
    sentiment: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    confidence: float | None = None


class AnalysisUpdate(BaseModel):
    """Schema for updating an existing analysis."""

    is_pending: bool | None = None
    category: str | None = None
    priority_score: float | None = None
    spam_score: float | None = None
    is_phishing: bool | None = None
    summary: str | None = None
    action_items: list[ActionItem] | None = None
    extracted_dates: list[ExtractedDate] | None = None
    extracted_entities: dict[str, list[str]] | None = None
    suggested_action: str | None = None
    sentiment: str | None = None
    confidence: float | None = None






class AnalysisResponse(BaseModel):
    """API response for an email analysis."""

    email_id: str
    is_pending: bool
    category: str | None
    priority_score: float | None
    spam_score: float | None
    is_phishing: bool
    summary: str | None
    action_items: list[ActionItem]
    extracted_dates: list[ExtractedDate]
    extracted_entities: dict[str, list[str]]
    suggested_action: str | None
    sentiment: str | None
    model_name: str | None
    prompt_version: str | None
    confidence: float | None
    analyzed_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("action_items", mode="before")
    @classmethod
    def parse_action_items(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v

    @field_validator("extracted_dates", mode="before")
    @classmethod
    def parse_extracted_dates(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v

    @field_validator("extracted_entities", mode="before")
    @classmethod
    def parse_extracted_entities(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v
