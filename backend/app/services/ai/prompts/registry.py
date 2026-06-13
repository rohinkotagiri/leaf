"""Central registry for versioned AI prompts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PromptTemplate(BaseModel):
    """A named, versioned prompt template."""

    name: str
    version: str
    system: str
    user_template: str
    output_schema: dict[str, Any] | None = None

    def render(self, **kwargs: Any) -> str:
        """Render the user prompt with strict Python format placeholders."""
        return self.user_template.format(**kwargs)


class PromptRegistry:
    """Central prompt registry for all AI services."""

    CLASSIFY_V1 = "classify_v1"
    SUMMARIZE_V1 = "summarize_v1"
    EXTRACT_V1 = "extract_v1"
    SPAM_V1 = "spam_v1"

    prompts: dict[str, PromptTemplate] = {
        CLASSIFY_V1: PromptTemplate(
            name=CLASSIFY_V1,
            version=CLASSIFY_V1,
            system=(
                "You are a fast privacy-preserving email classifier. "
                "Return valid JSON only and do not include commentary."
            ),
            user_template=(
                "Classify this email using one of these categories: {categories}.\n\n"
                "User correction examples:\n{few_shot_examples}\n\n"
                "Email:\n"
                "Subject: {subject}\n"
                "Sender: {sender}\n"
                "Body preview: {body_preview}\n\n"
                "Return JSON only with keys: category, priority_score, spam_score, "
                "is_phishing, suggested_action, confidence. Scores must be 0.0 to 1.0."
            ),
        ),
        SUMMARIZE_V1: PromptTemplate(
            name=SUMMARIZE_V1,
            version=SUMMARIZE_V1,
            system=(
                "You summarize emails clearly and compactly for a local mail assistant. "
                "Keep private details intact and avoid speculation."
            ),
            user_template=(
                "{task}\n\n"
                "Subject: {subject}\n"
                "Sender: {sender}\n"
                "Content:\n{content}"
            ),
        ),
        EXTRACT_V1: PromptTemplate(
            name=EXTRACT_V1,
            version=EXTRACT_V1,
            system=(
                "You extract structured facts from emails. Return valid JSON only. "
                "Use empty lists when a field is absent."
            ),
            user_template=(
                "Extract action items, appointments, commitments, and named entities.\n\n"
                "Subject: {subject}\n"
                "Sender: {sender}\n"
                "Body:\n{body}\n\n"
                "Return JSON with this shape: "
                "{{\"action_items\": [{{\"task\": \"\", \"deadline\": null, \"priority\": null}}], "
                "\"appointments\": [{{\"title\": \"\", \"date\": null, \"time\": null, "
                "\"location\": null, \"attendees\": []}}], "
                "\"commitments\": [{{\"description\": \"\", \"owner\": null, \"due_date\": null}}], "
                "\"entities\": {{\"people\": [], \"organizations\": [], \"monetary_amounts\": []}}, "
                "\"confidence\": 0.0}}"
            ),
        ),
        SPAM_V1: PromptTemplate(
            name=SPAM_V1,
            version=SPAM_V1,
            system=(
                "You detect phishing and spam indicators in email text. "
                "Return valid JSON only."
            ),
            user_template=(
                "Assess whether this email body contains phishing or spam patterns.\n\n"
                "Subject: {subject}\n"
                "Sender: {sender}\n"
                "Body:\n{body}\n\n"
                "Return JSON with keys: spam_score, is_phishing, reasons, confidence. "
                "Scores must be 0.0 to 1.0."
            ),
        ),
    }

    @classmethod
    def get(cls, prompt_id: str) -> PromptTemplate:
        """Return a registered prompt template by id."""
        return cls.prompts[prompt_id]
