"""Shared helpers for local AI services."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

WHITESPACE_RE = re.compile(r"\s+")


def clean_whitespace(text: str | None) -> str:
    """Normalize repeated whitespace without changing word order."""
    if not text:
        return ""
    return WHITESPACE_RE.sub(" ", text).strip()


def truncate_tokens(text: str, max_tokens: int) -> str:
    """Approximate token truncation using whitespace-separated words."""
    tokens = clean_whitespace(text).split()
    if len(tokens) <= max_tokens:
        return " ".join(tokens)
    return " ".join(tokens[:max_tokens])


def smart_truncate_tokens(text: str, head_tokens: int = 2000, tail_tokens: int = 500) -> str:
    """Keep the beginning and end of long text for summary/extraction prompts."""
    tokens = clean_whitespace(text).split()
    budget = head_tokens + tail_tokens
    if len(tokens) <= budget:
        return " ".join(tokens)
    head = " ".join(tokens[:head_tokens])
    tail = " ".join(tokens[-tail_tokens:])
    return f"{head}\n\n[... middle omitted ...]\n\n{tail}"


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    """Yield list chunks of a fixed maximum size."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def response_content(response: Any) -> str:
    """Extract chat content from Ollama SDK dict-like or object responses."""
    if isinstance(response, dict):
        message = response.get("message", {})
        if isinstance(message, dict):
            return str(message.get("content", ""))
        return str(getattr(message, "content", ""))

    message = getattr(response, "message", None)
    if isinstance(message, dict):
        return str(message.get("content", ""))
    if message is not None:
        return str(getattr(message, "content", ""))
    return ""


def generate_content(response: Any) -> str:
    """Extract generate content from Ollama SDK dict-like or object responses."""
    if isinstance(response, dict):
        return str(response.get("response", ""))
    return str(getattr(response, "response", ""))


def response_embeddings(response: Any) -> list[list[float]]:
    """Extract embeddings from Ollama SDK dict-like or object responses."""
    if isinstance(response, dict):
        embeddings = response.get("embeddings")
        if embeddings is None and "embedding" in response:
            embeddings = [response["embedding"]]
    else:
        embeddings = getattr(response, "embeddings", None)
        if embeddings is None and hasattr(response, "embedding"):
            embeddings = [response.embedding]

    if embeddings is None:
        raise ValueError("Ollama embed response did not include embeddings")
    return [[float(value) for value in vector] for vector in embeddings]


def parse_json_object(content: str) -> dict[str, Any]:
    """Parse JSON object content, accepting common fenced JSON output."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data
