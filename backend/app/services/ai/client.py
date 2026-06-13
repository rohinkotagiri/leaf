"""Async retry-safe wrapper around the Ollama Python SDK."""

# ruff: noqa: ASYNC109

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from app.config import settings

try:  # pragma: no cover - exercised only when dependency is missing
    from ollama import AsyncClient
except ImportError:  # pragma: no cover
    AsyncClient = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class OllamaClientError(RuntimeError):
    """Raised when an Ollama request fails after retry handling."""


class OllamaModelUnavailableError(OllamaClientError):
    """Raised when a required local model is not available."""


class OllamaClient:
    """Thin async client that centralizes retries, timeouts, and model checks."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client: Any | None = None,
        max_retries: int | None = None,
        retry_delays: Sequence[float] | None = None,
        default_timeout: float | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.max_retries = settings.AI_MAX_RETRIES if max_retries is None else max_retries
        self.retry_delays = tuple(retry_delays or (1.0, 2.0, 4.0))
        self.default_timeout = default_timeout or float(settings.OLLAMA_TIMEOUT)
        self._sleep = sleep or asyncio.sleep

        if client is not None:
            self._client = client
        else:
            if AsyncClient is None:
                raise OllamaClientError("The 'ollama' package is not installed")
            self._client = AsyncClient(host=self.base_url, timeout=self.default_timeout)

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        timeout: float | None = None,
        format: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Run a non-streaming chat request."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [dict(message) for message in messages],
            "stream": False,
        }
        if format is not None:
            kwargs["format"] = format
        if options is not None:
            kwargs["options"] = options

        return await self._request_with_retries(
            lambda: self._client.chat(**kwargs),
            timeout=timeout,
            operation="chat",
        )

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        timeout: float | None = None,
        format: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Run a non-streaming generate request."""
        kwargs: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if format is not None:
            kwargs["format"] = format
        if options is not None:
            kwargs["options"] = options

        return await self._request_with_retries(
            lambda: self._client.generate(**kwargs),
            timeout=timeout,
            operation="generate",
        )

    async def embed(
        self,
        *,
        model: str,
        input: str | list[str],
        timeout: float | None = None,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Generate embeddings for one string or a batch of strings."""
        kwargs: dict[str, Any] = {"model": model, "input": input}
        if options is not None:
            kwargs["options"] = options
        return await self._request_with_retries(
            lambda: self._client.embed(**kwargs),
            timeout=timeout,
            operation="embed",
        )

    async def is_running(self) -> bool:
        """Return True when the Ollama server responds to a model list request."""
        try:
            await self._request_with_retries(
                lambda: self._client.list(),
                timeout=5.0,
                operation="list",
            )
        except OllamaClientError:
            return False
        return True

    async def ensure_model_available(self, model_name: str) -> bool:
        """Check that a model exists locally; this method does not pull models."""
        response = await self._request_with_retries(
            lambda: self._client.list(),
            timeout=10.0,
            operation="list",
        )
        names = self._extract_model_names(response)
        if model_name not in names:
            raise OllamaModelUnavailableError(
                f"Ollama model '{model_name}' is not available locally"
            )
        return True

    async def _request_with_retries(
        self,
        factory: Callable[[], Awaitable[Any]],
        *,
        timeout: float | None,
        operation: str,
    ) -> Any:
        request_timeout = self.default_timeout if timeout is None else timeout
        last_exc: BaseException | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await asyncio.wait_for(factory(), timeout=request_timeout)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break

                delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                logger.warning(
                    "Ollama %s failed on attempt %d/%d; retrying in %.1fs",
                    operation,
                    attempt + 1,
                    self.max_retries + 1,
                    delay,
                    exc_info=True,
                )
                await self._sleep(delay)

        raise OllamaClientError(
            f"Ollama {operation} failed after {self.max_retries + 1} attempts"
        ) from last_exc

    @staticmethod
    def _extract_model_names(response: Any) -> set[str]:
        if isinstance(response, dict):
            models = response.get("models", [])
        else:
            models = getattr(response, "models", [])

        names: set[str] = set()
        for model in models:
            if isinstance(model, dict):
                name = model.get("model") or model.get("name")
            else:
                name = getattr(model, "model", None) or getattr(model, "name", None)
            if name:
                names.add(str(name))
        return names
