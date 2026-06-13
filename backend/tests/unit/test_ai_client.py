"""Unit tests for the Ollama client wrapper."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.services.ai.client import OllamaClient, OllamaClientError, OllamaModelUnavailableError


class FakeOllamaSDK:
    """Small async fake that mimics the SDK methods used by OllamaClient."""

    def __init__(self, *, failures_before_success: int = 0, list_fails: bool = False) -> None:
        self.failures_before_success = failures_before_success
        self.list_fails = list_fails
        self.chat_attempts = 0
        self.list_attempts = 0

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.chat_attempts += 1
        if self.chat_attempts <= self.failures_before_success:
            raise RuntimeError("temporary failure")
        return {"message": {"content": "ok"}, "kwargs": kwargs}

    async def generate(self, **kwargs: Any) -> dict[str, Any]:
        return {"response": "generated", "kwargs": kwargs}

    async def embed(self, **kwargs: Any) -> dict[str, Any]:
        return {"embeddings": [[0.1, 0.2]], "kwargs": kwargs}

    async def list(self) -> dict[str, Any]:
        self.list_attempts += 1
        if self.list_fails:
            raise RuntimeError("not running")
        return {"models": [{"model": "llama3.2:3b"}, {"name": "mistral:7b"}]}


async def no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_chat_retries_then_succeeds() -> None:
    sdk = FakeOllamaSDK(failures_before_success=2)
    client = OllamaClient(client=sdk, max_retries=3, retry_delays=(0, 0, 0), sleep=no_sleep)

    response = await client.chat(
        model="llama3.2:3b",
        messages=[{"role": "user", "content": "hello"}],
        timeout=1,
    )

    assert response["message"]["content"] == "ok"
    assert sdk.chat_attempts == 3


@pytest.mark.asyncio
async def test_chat_timeout_is_wrapped_after_retries() -> None:
    class SlowSDK(FakeOllamaSDK):
        async def chat(self, **kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(0.05)
            return {"message": {"content": "late"}, "kwargs": kwargs}

    client = OllamaClient(client=SlowSDK(), max_retries=0, retry_delays=(0,), sleep=no_sleep)

    with pytest.raises(OllamaClientError):
        await client.chat(
            model="llama3.2:3b",
            messages=[{"role": "user", "content": "hello"}],
            timeout=0.001,
        )


@pytest.mark.asyncio
async def test_health_and_model_checks() -> None:
    client = OllamaClient(client=FakeOllamaSDK(), max_retries=0, retry_delays=(0,), sleep=no_sleep)

    assert await client.is_running() is True
    assert await client.ensure_model_available("mistral:7b") is True

    with pytest.raises(OllamaModelUnavailableError):
        await client.ensure_model_available("missing:model")


@pytest.mark.asyncio
async def test_is_running_false_when_list_fails() -> None:
    client = OllamaClient(
        client=FakeOllamaSDK(list_fails=True),
        max_retries=0,
        retry_delays=(0,),
        sleep=no_sleep,
    )

    assert await client.is_running() is False
