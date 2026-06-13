"""Fast email classification service."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email import Email
from app.models.feedback import UserFeedback
from app.services.ai.client import OllamaClient
from app.services.ai.prompts import PromptRegistry
from app.services.ai.schemas import MVP_CATEGORIES, ClassificationResult
from app.services.ai.utils import clean_whitespace, parse_json_object, response_content

logger = logging.getLogger(__name__)

CLASSIFICATION_FEEDBACK_FIELDS = {
    "category",
    "priority_score",
    "spam_score",
    "is_phishing",
    "suggested_action",
}


class ClassificationService:
    """Classify email priority, category, and spam risk quickly."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        timeout: float | None = None,
        prompt_registry: type[PromptRegistry] = PromptRegistry,
        max_invalid_json_retries: int | None = None,
    ) -> None:
        self.client = client or OllamaClient()
        self.model = model or settings.OLLAMA_FAST_MODEL
        self.timeout = timeout or float(settings.OLLAMA_FAST_TIMEOUT)
        self.prompt_registry = prompt_registry
        self.max_invalid_json_retries = (
            settings.AI_MAX_RETRIES if max_invalid_json_retries is None else max_invalid_json_retries
        )

    async def classify_email(
        self,
        subject: str,
        sender: str,
        body: str,
        *,
        session: AsyncSession | None = None,
    ) -> ClassificationResult:
        """Classify an email using only lightweight metadata and a body preview."""
        clean_subject = clean_whitespace(subject)
        clean_sender = clean_whitespace(sender)
        body_preview = clean_whitespace(body)[:300]
        prompt = self.prompt_registry.get(PromptRegistry.CLASSIFY_V1)
        few_shot_examples = await self._load_few_shot_examples(session)

        user_prompt = prompt.render(
            categories=", ".join(MVP_CATEGORIES),
            few_shot_examples=few_shot_examples or "No user correction examples yet.",
            subject=clean_subject,
            sender=clean_sender,
            body_preview=body_preview,
        )
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": user_prompt},
        ]

        last_error: Exception | None = None
        for attempt in range(self.max_invalid_json_retries + 1):
            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    timeout=self.timeout,
                    format="json",
                    options={"temperature": 0},
                )
                data = parse_json_object(response_content(response))
                return ClassificationResult.model_validate(data)
            except (ValueError, ValidationError) as exc:
                last_error = exc
                logger.warning(
                    "Invalid classification JSON on attempt %d/%d",
                    attempt + 1,
                    self.max_invalid_json_retries + 1,
                    exc_info=True,
                )
            except Exception as exc:
                last_error = exc
                logger.warning("Classification request failed; returning fallback", exc_info=True)
                break

        logger.error("Classification failed after retries; using fallback: %s", last_error)
        return self.fallback_result()

    @staticmethod
    def fallback_result() -> ClassificationResult:
        """Safe fallback when the model response cannot be used."""
        return ClassificationResult(
            category="other",
            priority_score=0.0,
            spam_score=0.0,
            is_phishing=False,
            suggested_action="review_manually",
            confidence=0.0,
        )

    async def _load_few_shot_examples(self, session: AsyncSession | None) -> str:
        if session is None:
            return ""

        stmt = (
            select(UserFeedback, Email)
            .join(Email, UserFeedback.email_id == Email.id)
            .where(UserFeedback.field.in_(CLASSIFICATION_FEEDBACK_FIELDS))
            .order_by(UserFeedback.created_at.desc())
            .limit(5)
        )
        result = await session.execute(stmt)
        examples: list[str] = []
        for feedback, email in result.all():
            examples.append(
                "\n".join(
                    [
                        f"Subject: {clean_whitespace(email.subject)}",
                        f"Sender: {clean_whitespace(email.sender_email)}",
                        f"Body preview: {clean_whitespace(email.body_text)[:160]}",
                        f"Corrected {feedback.field}: {feedback.new_value}",
                    ]
                )
            )
        return "\n\n".join(examples)
