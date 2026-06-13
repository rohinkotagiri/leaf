"""Deterministic Ollama client test double."""

# ruff: noqa: ASYNC109

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.config import settings
from app.services.ai.client import OllamaModelUnavailableError


class MockOllamaClient:
    """Mock client with the same async surface as OllamaClient."""

    def __init__(
        self,
        *,
        chat_responses: Sequence[str | dict[str, Any]] | None = None,
        generate_responses: Sequence[str | dict[str, Any]] | None = None,
        running: bool = True,
        models: Sequence[str] | None = None,
        embedding_dimensions: int = 8,
    ) -> None:
        self.chat_responses = list(chat_responses or [])
        self.generate_responses = list(generate_responses or [])
        self.running = running
        self.models = set(
            models
            or [
                settings.OLLAMA_FAST_MODEL,
                settings.OLLAMA_CHAT_MODEL,
                settings.OLLAMA_EMBED_MODEL,
            ]
        )
        self.embedding_dimensions = embedding_dimensions
        self.chat_calls: list[dict[str, Any]] = []
        self.generate_calls: list[dict[str, Any]] = []
        self.embed_calls: list[dict[str, Any]] = []

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        timeout: float | None = None,
        format: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.chat_calls.append(
            {
                "model": model,
                "messages": [dict(message) for message in messages],
                "timeout": timeout,
                "format": format,
                "options": options,
            }
        )
        content = self._next_chat_content(messages)
        return {"model": model, "message": {"role": "assistant", "content": content}}

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        timeout: float | None = None,
        format: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.generate_calls.append(
            {
                "model": model,
                "prompt": prompt,
                "timeout": timeout,
                "format": format,
                "options": options,
            }
        )
        if self.generate_responses:
            content = self.generate_responses.pop(0)
        else:
            content = "Generated response."
        return {"model": model, "response": self._content_to_string(content)}

    async def embed(
        self,
        *,
        model: str,
        input: str | list[str],
        timeout: float | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.embed_calls.append(
            {
                "model": model,
                "input": input,
                "timeout": timeout,
                "options": options,
            }
        )
        texts = [input] if isinstance(input, str) else input
        return {"model": model, "embeddings": [self._embedding_for(text) for text in texts]}

    async def is_running(self) -> bool:
        return self.running

    async def ensure_model_available(self, model_name: str) -> bool:
        if not self.running or model_name not in self.models:
            raise OllamaModelUnavailableError(f"Ollama model '{model_name}' is not available locally")
        return True

    def _next_chat_content(self, messages: Sequence[Mapping[str, str]]) -> str:
        if self.chat_responses:
            return self._content_to_string(self.chat_responses.pop(0))

        joined = "\n".join(message.get("content", "") for message in messages).lower()
        if "classify this email" in joined:
            return json.dumps(
                {
                    "category": "work",
                    "priority_score": 0.7,
                    "spam_score": 0.05,
                    "is_phishing": False,
                    "suggested_action": "reply_when_available",
                    "confidence": 0.86,
                }
            )
        if "extract action items" in joined:
            return json.dumps(
                {
                    "action_items": [{"task": "Send the report", "deadline": "Friday", "priority": "high"}],
                    "appointments": [],
                    "commitments": [{"description": "Sender will review the draft", "owner": "sender"}],
                    "entities": {
                        "people": ["Alice"],
                        "organizations": ["Acme Corp"],
                        "monetary_amounts": [],
                    },
                    "confidence": 0.82,
                }
            )
        if "key_points" in joined:
            return json.dumps({"key_points": ["Project update requested", "Deadline is Friday"]})
        if "phishing or spam patterns" in joined:
            return json.dumps(
                {
                    "spam_score": 0.2,
                    "is_phishing": False,
                    "reasons": ["No urgent credential request"],
                    "confidence": 0.8,
                }
            )
        return "This email asks for a report update and mentions a Friday deadline."

    @staticmethod
    def _content_to_string(content: str | dict[str, Any]) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content)

    def _embedding_for(self, text: str) -> list[float]:
        seed = sum(ord(char) for char in text) or 1
        return [
            round(((seed + index * 17) % 100) / 100, 4)
            for index in range(self.embedding_dimensions)
        ]
