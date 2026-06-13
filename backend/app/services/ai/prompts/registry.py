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
    PARSE_QUERY_V1 = "parse_query_v1"

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
        PARSE_QUERY_V1: PromptTemplate(
            name=PARSE_QUERY_V1,
            version=PARSE_QUERY_V1,
            system=(
                "You are a structured search query parser. Your job is to extract search filters "
                "and keywords from a natural language query. Return valid JSON only and do not "
                "include commentary."
            ),
            user_template=(
                "Analyze the following natural language search query and extract search filters and keywords.\n"
                "Current Local Time: {current_time}\n\n"
                "Extract the following keys in JSON format:\n"
                "- \"keywords\": A list of search term strings (exclude terms used for structural filters like dates or folders).\n"
                "- \"date_from\": The starting date filter in YYYY-MM-DD format (resolve relative ranges like 'last 3 months', 'yesterday', 'last week' relative to Current Local Time). Use null if no start date is specified.\n"
                "- \"date_to\": The ending date filter in YYYY-MM-DD format. Use null if no end date is specified.\n"
                "- \"sender_filter\": A string of a sender's name or email to filter by. Use null if none.\n"
                "- \"category_filter\": The name of the category to filter by (one of: work, personal, finance, travel, shopping, newsletter, notification, security, spam, other). Use null if none.\n"
                "- \"has_attachments\": A boolean indicating if the query asks for emails with attachments. Use null if not specified.\n"
                "- \"is_unread\": A boolean indicating if the query asks for unread/read status. Use null if not specified.\n\n"
                "Query: \"{query}\"\n\n"
                "Return JSON only. Do not wrap in markdown or add notes."
            ),
        ),
    }

    @classmethod
    def get(cls, prompt_id: str) -> PromptTemplate:
        """Return a registered prompt template by id."""
        return cls.prompts[prompt_id]
