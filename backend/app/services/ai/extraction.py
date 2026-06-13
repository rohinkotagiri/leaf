"""Structured deep extraction service."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.services.ai.client import OllamaClient
from app.services.ai.prompts import PromptRegistry
from app.services.ai.schemas import ExtractionResult
from app.services.ai.utils import (
    clean_whitespace,
    parse_json_object,
    response_content,
    smart_truncate_tokens,
)

logger = logging.getLogger(__name__)


class ExtractionService:
    """Extract action items, appointments, commitments, and named entities."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        timeout: float | None = None,
        prompt_registry: type[PromptRegistry] = PromptRegistry,
    ) -> None:
        self.client = client or OllamaClient()
        self.model = model or settings.OLLAMA_CHAT_MODEL
        self.timeout = timeout or float(settings.OLLAMA_DEEP_TIMEOUT)
        self.prompt_registry = prompt_registry

    async def extract_email(self, subject: str, sender: str, body: str) -> ExtractionResult:
        """Extract structured facts from one email."""
        prompt = self.prompt_registry.get(PromptRegistry.EXTRACT_V1)
        user_prompt = prompt.render(
            subject=clean_whitespace(subject),
            sender=clean_whitespace(sender),
            body=smart_truncate_tokens(body),
        )
        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=self.timeout,
                format="json",
                options={"temperature": 0},
            )
            return ExtractionResult.model_validate(parse_json_object(response_content(response)))
        except Exception:
            logger.warning("Extraction failed; returning empty extraction result", exc_info=True)
            return ExtractionResult(confidence=0.0)
