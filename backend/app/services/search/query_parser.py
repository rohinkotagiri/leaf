"""Natural Language query parsing service using Ollama LLM and Regex fallbacks."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.config import settings
from app.services.ai.client import OllamaClient
from app.services.ai.prompts import PromptRegistry
from app.services.ai.utils import clean_whitespace, parse_json_object, response_content

logger = logging.getLogger(__name__)


class ParsedQuery(BaseModel):
    """Structured representation of parsed search query parameters."""

    keywords: list[str] = Field(default_factory=list)
    date_from: str | None = None  # YYYY-MM-DD format
    date_to: str | None = None    # YYYY-MM-DD format
    sender_filter: str | None = None
    category_filter: str | None = None
    has_attachments: bool | None = None
    is_unread: bool | None = None


class QueryParser:
    """Parses natural language queries into structured filters."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        timeout: float | None = None,
        prompt_registry: type[PromptRegistry] = PromptRegistry,
    ) -> None:
        self.client = client or OllamaClient()
        self.model = model or settings.OLLAMA_CHAT_MODEL  # Defaults to mistral:7b
        self.timeout = timeout or float(settings.OLLAMA_DEEP_TIMEOUT)
        self.prompt_registry = prompt_registry

    async def parse(self, query: str) -> ParsedQuery:
        """Parse natural language query into filters. Falls back to Regex parser if LLM fails."""
        if not query.strip():
            return ParsedQuery()

        try:
            current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            prompt = self.prompt_registry.get(PromptRegistry.PARSE_QUERY_V1)
            user_prompt = prompt.render(
                current_time=current_time_str,
                query=query.strip(),
            )
            messages = [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": user_prompt},
            ]

            response = await self.client.chat(
                model=self.model,
                messages=messages,
                timeout=self.timeout,
                format="json",
                options={"temperature": 0},
            )
            data = parse_json_object(response_content(response))
            parsed = ParsedQuery.model_validate(data)
            logger.info("Successfully parsed query via LLM: %s -> %s", query, parsed.model_dump())
            return parsed
        except Exception as e:
            logger.warning("LLM query parsing failed, falling back to Regex parser: %s", str(e))
            return self.parse_regex(query)

    def parse_regex(self, query: str) -> ParsedQuery:
        """Fallback Regex parser for extracting structured query properties."""
        keywords: list[str] = []
        date_from: str | None = None
        date_to: str | None = None
        sender_filter: str | None = None
        category_filter: str | None = None
        has_attachments: bool | None = None
        is_unread: bool | None = None

        # Work with a copy we can strip filters from
        temp_query = query

        # 1. Extract from:(\S+) or from:"([^"]+)"
        sender_match = re.search(r'\bfrom:(?:"([^"]+)"|(\S+))', temp_query, re.IGNORECASE)
        if sender_match:
            sender_filter = sender_match.group(1) or sender_match.group(2)
            temp_query = re.sub(r'\bfrom:(?:"[^"]+"|\S+)', '', temp_query, flags=re.IGNORECASE)

        # 2. Extract before:(\S+) / after:(\S+)
        before_match = re.search(r'\bbefore:(\S+)', temp_query, re.IGNORECASE)
        if before_match:
            date_to = self._resolve_date_string(before_match.group(1))
            temp_query = re.sub(r'\bbefore:\S+', '', temp_query, flags=re.IGNORECASE)

        after_match = re.search(r'\bafter:(\S+)', temp_query, re.IGNORECASE)
        if after_match:
            date_from = self._resolve_date_string(after_match.group(1))
            temp_query = re.sub(r'\bafter:\S+', '', temp_query, flags=re.IGNORECASE)

        # 3. Extract in:(\S+) or category:(\S+)
        cat_match = re.search(r'\b(?:in|category):(\S+)', temp_query, re.IGNORECASE)
        if cat_match:
            category_filter = cat_match.group(1).lower()
            temp_query = re.sub(r'\b(?:in|category):\S+', '', temp_query, flags=re.IGNORECASE)

        # 4. Extract has:attachment or has:attachments
        attachment_match = re.search(r'\bhas:attachments?\b', temp_query, re.IGNORECASE)
        if attachment_match:
            has_attachments = True
            temp_query = re.sub(r'\bhas:attachments?\b', '', temp_query, flags=re.IGNORECASE)

        # 5. Extract is:unread or is:read
        unread_match = re.search(r'\bis:(unread|read)\b', temp_query, re.IGNORECASE)
        if unread_match:
            is_unread = (unread_match.group(1).lower() == "unread")
            temp_query = re.sub(r'\bis:(?:unread|read)\b', '', temp_query, flags=re.IGNORECASE)

        # Clean remaining text into keywords
        clean_text = clean_whitespace(temp_query)
        if clean_text:
            keywords = [w.strip() for w in clean_text.split(" ") if w.strip()]

        return ParsedQuery(
            keywords=keywords,
            date_from=date_from,
            date_to=date_to,
            sender_filter=sender_filter,
            category_filter=category_filter,
            has_attachments=has_attachments,
            is_unread=is_unread,
        )

    def _resolve_date_string(self, date_str: str) -> str | None:
        """Resolve query date filters like YYYY-MM-DD or relative like '30d', '3m', '1y'."""
        date_str = date_str.lower().strip()
        # Direct YYYY-MM-DD check
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        # Relative values
        m = re.match(r'^(\d+)(d|w|m|y)$', date_str)
        if m:
            val = int(m.group(1))
            unit = m.group(2)
            today = datetime.now()

            if unit == 'd':
                delta = timedelta(days=val)
            elif unit == 'w':
                delta = timedelta(weeks=val)
            elif unit == 'm':
                delta = timedelta(days=val * 30)
            else:  # 'y'
                delta = timedelta(days=val * 365)

            target_date = today - delta
            return target_date.strftime("%Y-%m-%d")

        return None
