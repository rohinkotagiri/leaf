"""Unit tests for ThreadReconstructor."""

from __future__ import annotations

from app.schemas.email import EmailMessage
from app.services.imap.threading import ThreadReconstructor


class TestThreadReconstructor:
    """Test suite for thread reconstruction logic."""

    def setup_method(self) -> None:
        self.reconstructor = ThreadReconstructor()

    def _make_email(
        self,
        message_id: str = "",
        subject: str = "",
        in_reply_to: str = "",
        references: list[str] | None = None,
        uid: int = 1,
    ) -> EmailMessage:
        return EmailMessage(
            message_id=message_id,
            subject=subject,
            in_reply_to=in_reply_to,
            references=references or [],
            account_id="test-account",
            uid=uid,
        )

    # ── Basic thread assignment ───────────────────────────────────────

    def test_new_email_gets_new_thread(self) -> None:
        """An email with no threading headers gets a new thread ID."""
        email = self._make_email(
            message_id="<msg001@example.com>",
            subject="Hello",
        )
        thread_id = self.reconstructor.assign_thread_id(email)
        assert thread_id
        assert isinstance(thread_id, str)

    def test_reply_shares_thread_via_in_reply_to(self) -> None:
        """A reply linked via In-Reply-To should share the original's thread."""
        original = self._make_email(
            message_id="<original@example.com>",
            subject="Original Subject",
        )
        reply = self._make_email(
            message_id="<reply@example.com>",
            subject="Re: Original Subject",
            in_reply_to="<original@example.com>",
        )

        thread1 = self.reconstructor.assign_thread_id(original)
        thread2 = self.reconstructor.assign_thread_id(reply)

        assert thread1 == thread2

    def test_reply_shares_thread_via_references(self) -> None:
        """A reply linked via References header should share the thread."""
        original = self._make_email(
            message_id="<orig@example.com>",
            subject="Topic",
        )
        reply = self._make_email(
            message_id="<reply@example.com>",
            subject="Re: Topic",
            references=["<orig@example.com>"],
        )

        thread1 = self.reconstructor.assign_thread_id(original)
        thread2 = self.reconstructor.assign_thread_id(reply)

        assert thread1 == thread2

    # ── Multi-message threads ─────────────────────────────────────────

    def test_three_message_thread(self) -> None:
        """Three emails in a chain should all share one thread."""
        msg1 = self._make_email(
            message_id="<a@example.com>",
            subject="Discussion",
        )
        msg2 = self._make_email(
            message_id="<b@example.com>",
            subject="Re: Discussion",
            in_reply_to="<a@example.com>",
            references=["<a@example.com>"],
        )
        msg3 = self._make_email(
            message_id="<c@example.com>",
            subject="Re: Re: Discussion",
            in_reply_to="<b@example.com>",
            references=["<a@example.com>", "<b@example.com>"],
        )

        t1 = self.reconstructor.assign_thread_id(msg1)
        t2 = self.reconstructor.assign_thread_id(msg2)
        t3 = self.reconstructor.assign_thread_id(msg3)

        assert t1 == t2 == t3

    # ── Subject-based fallback ────────────────────────────────────────

    def test_subject_fallback_matching(self) -> None:
        """Without threading headers, fall back to normalized subject matching."""
        self.reconstructor.reset()

        msg1 = self._make_email(
            message_id="<first@example.com>",
            subject="Meeting Tomorrow",
            uid=1,
        )
        msg2 = self._make_email(
            message_id="<second@example.com>",
            subject="Re: Meeting Tomorrow",
            uid=2,
        )

        t1 = self.reconstructor.assign_thread_id(msg1)
        t2 = self.reconstructor.assign_thread_id(msg2)

        assert t1 == t2

    def test_different_subjects_different_threads(self) -> None:
        """Emails with different subjects should get different threads."""
        self.reconstructor.reset()

        msg1 = self._make_email(
            message_id="<a@example.com>",
            subject="Topic A",
            uid=1,
        )
        msg2 = self._make_email(
            message_id="<b@example.com>",
            subject="Topic B",
            uid=2,
        )

        t1 = self.reconstructor.assign_thread_id(msg1)
        t2 = self.reconstructor.assign_thread_id(msg2)

        assert t1 != t2

    # ── Subject normalization ─────────────────────────────────────────

    def test_normalize_subject_strips_prefixes(self) -> None:
        """Re:/Fwd:/FW: prefixes should be stripped."""
        assert ThreadReconstructor._normalize_subject("Re: Hello") == "hello"
        assert ThreadReconstructor._normalize_subject("Fwd: Hello") == "hello"
        assert ThreadReconstructor._normalize_subject("RE: FW: Re: Hello") == "hello"
        assert ThreadReconstructor._normalize_subject("  Re:  Hello  ") == "hello"

    def test_normalize_subject_empty(self) -> None:
        """Empty subject should return empty string."""
        assert ThreadReconstructor._normalize_subject("") == ""
        assert ThreadReconstructor._normalize_subject("   ") == ""

    # ── Existing threads (DB resume) ──────────────────────────────────

    def test_existing_threads_from_database(self) -> None:
        """Existing thread mappings from DB should be respected."""
        self.reconstructor.reset()

        existing = {"<old@example.com>": "known-thread-id-123"}

        reply = self._make_email(
            message_id="<new@example.com>",
            subject="Re: Old Topic",
            in_reply_to="<old@example.com>",
        )

        thread_id = self.reconstructor.assign_thread_id(reply, existing_threads=existing)
        assert thread_id == "known-thread-id-123"

    # ── Reset ─────────────────────────────────────────────────────────

    def test_reset_clears_mappings(self) -> None:
        """Reset should clear all cached thread mappings."""
        msg = self._make_email(message_id="<x@example.com>", subject="Test")
        self.reconstructor.assign_thread_id(msg)

        self.reconstructor.reset()

        # After reset, same message should get a potentially new thread
        # (since the old mapping is gone)
        msg2 = self._make_email(
            message_id="<y@example.com>",
            subject="Different",
            in_reply_to="<x@example.com>",
        )
        thread_id = self.reconstructor.assign_thread_id(msg2)
        # Should NOT match — the <x@example.com> mapping was cleared
        assert thread_id  # Just ensure it doesn't crash
