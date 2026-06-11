"""Thread reconstruction — groups emails into conversation threads.

Uses In-Reply-To and References headers to link related emails.
Falls back to normalized subject matching when headers are missing.
"""

from __future__ import annotations

import logging
import re
import uuid

from app.schemas.email import EmailMessage

logger = logging.getLogger(__name__)


class ThreadReconstructor:
    """Assign thread IDs to emails based on their relationships."""

    def __init__(self) -> None:
        # Maps Message-ID → thread_id for known messages
        self._message_to_thread: dict[str, str] = {}
        # Maps normalized subject → thread_id for fallback matching
        self._subject_to_thread: dict[str, str] = {}

    def assign_thread_id(
        self,
        email_msg: EmailMessage,
        existing_threads: dict[str, str] | None = None,
    ) -> str:
        """Assign a thread_id to an email.

        Resolution order:
        1. Check if any of the References match a known thread
        2. Check if In-Reply-To matches a known thread
        3. Check if the email's own Message-ID already has a thread
        4. Fall back to normalized subject matching
        5. Create a new thread

        Args:
            email_msg: The email to assign a thread to.
            existing_threads: Optional mapping of Message-ID → thread_id
                from the database (for resuming across sessions).

        Returns:
            The assigned thread_id (a UUID string).
        """
        if existing_threads:
            self._message_to_thread.update(existing_threads)

        thread_id: str | None = None

        # 1. Check References header (most reliable — ordered chain of Message-IDs)
        for ref in email_msg.references:
            ref_clean = ref.strip()
            if ref_clean in self._message_to_thread:
                thread_id = self._message_to_thread[ref_clean]
                logger.debug(
                    "Thread matched via References: %s → %s", ref_clean[:30], thread_id[:8]
                )
                break

        # 2. Check In-Reply-To header
        if not thread_id and email_msg.in_reply_to:
            reply_to = email_msg.in_reply_to.strip()
            if reply_to in self._message_to_thread:
                thread_id = self._message_to_thread[reply_to]
                logger.debug(
                    "Thread matched via In-Reply-To: %s → %s", reply_to[:30], thread_id[:8]
                )

        # 3. Check if this Message-ID already has a thread
        if not thread_id and email_msg.message_id:
            msg_id = email_msg.message_id.strip()
            if msg_id in self._message_to_thread:
                thread_id = self._message_to_thread[msg_id]

        # 4. Fall back to subject-based matching
        if not thread_id:
            normalized = self._normalize_subject(email_msg.subject)
            if normalized and normalized in self._subject_to_thread:
                thread_id = self._subject_to_thread[normalized]
                logger.debug(
                    "Thread matched via subject: '%s' → %s", normalized[:30], thread_id[:8]
                )

        # 5. Create a new thread
        if not thread_id:
            # Use UUID5 based on the earliest Message-ID for determinism
            seed = email_msg.message_id or f"{email_msg.account_id}:{email_msg.uid}"
            thread_id = str(uuid.uuid5(uuid.NAMESPACE_URL, seed))
            logger.debug("New thread created: %s for message %s", thread_id[:8], seed[:30])

        # Register this email's Message-ID in the lookup
        if email_msg.message_id:
            self._message_to_thread[email_msg.message_id.strip()] = thread_id

        # Register all References too
        for ref in email_msg.references:
            ref_clean = ref.strip()
            if ref_clean:
                self._message_to_thread[ref_clean] = thread_id

        # Register normalized subject
        normalized_subj = self._normalize_subject(email_msg.subject)
        if normalized_subj:
            self._subject_to_thread[normalized_subj] = thread_id

        return thread_id

    @staticmethod
    def _normalize_subject(subject: str) -> str:
        """Normalize subject by removing Re:/Fwd:/FW: prefixes and extra whitespace.

        Examples:
            "Re: Re: Fwd: Hello World" → "hello world"
            "RE: FW: Meeting Tomorrow" → "meeting tomorrow"
        """
        if not subject:
            return ""

        # Strip common reply/forward prefixes (case-insensitive, possibly repeated)
        normalized = re.sub(
            r"^(\s*(re|fwd|fw)\s*:\s*)+",
            "",
            subject,
            flags=re.IGNORECASE,
        )

        # Collapse whitespace and lowercase
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()

        return normalized

    def reset(self) -> None:
        """Clear all thread mappings (useful for testing)."""
        self._message_to_thread.clear()
        self._subject_to_thread.clear()
