"""Email and thread summarization service."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.config import settings
from app.schemas.email import EmailMessage
from app.services.ai.client import OllamaClient
from app.services.ai.prompts import PromptRegistry
from app.services.ai.utils import (
    clean_whitespace,
    parse_json_object,
    response_content,
    smart_truncate_tokens,
)

logger = logging.getLogger(__name__)


class SummarizationService:
    """Generate concise summaries and key points with the deep chat model."""

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

    async def summarize_email(self, subject: str, sender: str, body: str) -> str:
        """Return a 3-5 sentence summary for a single email."""
        prompt = self.prompt_registry.get(PromptRegistry.SUMMARIZE_V1)
        content = smart_truncate_tokens(body)
        user_prompt = prompt.render(
            task="Summarize this email in 3 to 5 sentences.",
            subject=clean_whitespace(subject),
            sender=clean_whitespace(sender),
            content=content,
        )
        return await self._chat_text(prompt.system, user_prompt)

    async def summarize_thread(self, messages: Sequence[EmailMessage]) -> str:
        """Return a chronological summary of all messages in a thread."""
        prompt = self.prompt_registry.get(PromptRegistry.SUMMARIZE_V1)
        ordered = sorted(messages, key=lambda message: message.date.timestamp() if message.date else 0)
        parts: list[str] = []
        for message in ordered:
            date = message.date.isoformat() if message.date else "unknown date"
            body = smart_truncate_tokens(message.body_text, head_tokens=600, tail_tokens=150)
            parts.append(
                "\n".join(
                    [
                        f"Date: {date}",
                        f"From: {message.sender_email}",
                        f"Subject: {message.subject}",
                        f"Body: {body}",
                    ]
                )
            )

        user_prompt = prompt.render(
            task="Summarize this email thread chronologically, noting decisions and open loops.",
            subject=ordered[-1].subject if ordered else "",
            sender=ordered[-1].sender_email if ordered else "",
            content="\n\n---\n\n".join(parts),
        )
        return await self._chat_text(prompt.system, user_prompt)

    async def extract_key_points(self, subject: str, sender: str, body: str) -> list[str]:
        """Return a bullet-like list of key points from an email."""
        prompt = self.prompt_registry.get(PromptRegistry.SUMMARIZE_V1)
        user_prompt = prompt.render(
            task=(
                "Extract the key points from this email. "
                "Return JSON only with a key_points array of short strings."
            ),
            subject=clean_whitespace(subject),
            sender=clean_whitespace(sender),
            content=smart_truncate_tokens(body),
        )
        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Return valid JSON only."},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=self.timeout,
                format="json",
                options={"temperature": 0},
            )
            data = parse_json_object(response_content(response))
            points = data.get("key_points", [])
            if isinstance(points, list):
                return [clean_whitespace(str(point)) for point in points if clean_whitespace(str(point))]
        except Exception:
            logger.warning("Key point JSON extraction failed; falling back to bullet parsing", exc_info=True)

        text = await self._chat_text(prompt.system, user_prompt)
        return self._parse_bullets(text)

    async def _chat_text(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=self.timeout,
            options={"temperature": 0.2},
        )
        return response_content(response).strip()

    @staticmethod
    def _parse_bullets(text: str) -> list[str]:
        points: list[str] = []
        for line in text.splitlines():
            cleaned = clean_whitespace(line).lstrip("-*0123456789. ")
            if cleaned:
                points.append(cleaned)
        return points
