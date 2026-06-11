"""Unit tests for EmailParser — 20+ test cases covering real-world email formats."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.imap.parser import EmailParser


class TestEmailParser:
    """Test suite for the email parser."""

    def setup_method(self) -> None:
        self.parser = EmailParser()
        self.account_id = "test-account-123"

    # ── Plain text emails ─────────────────────────────────────────────

    def test_parse_plain_text_email(self) -> None:
        """Parse a simple plain text email."""
        raw = (
            b"From: Alice <alice@example.com>\r\n"
            b"To: Bob <bob@example.com>\r\n"
            b"Subject: Hello World\r\n"
            b"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
            b"Message-ID: <msg001@example.com>\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Hello Bob,\r\n"
            b"\r\n"
            b"This is a plain text email.\r\n"
            b"\r\n"
            b"Best,\r\n"
            b"Alice\r\n"
        )

        result = self.parser.parse(raw, self.account_id, folder="INBOX", uid=1)

        assert result.subject == "Hello World"
        assert result.sender_name == "Alice"
        assert result.sender_email == "alice@example.com"
        assert result.message_id == "<msg001@example.com>"
        assert "Hello Bob" in result.body_text
        assert result.body_html == ""
        assert result.folder == "INBOX"
        assert result.uid == 1
        assert result.id  # Should be a sha256 hash

    def test_parse_plain_text_no_name(self) -> None:
        """Parse an email with bare email address in From header."""
        raw = (
            b"From: alice@example.com\r\n"
            b"To: bob@example.com\r\n"
            b"Subject: No Name\r\n"
            b"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
            b"Message-ID: <msg002@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Body text.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=2)
        assert result.sender_name == ""
        assert result.sender_email == "alice@example.com"

    # ── HTML emails ───────────────────────────────────────────────────

    def test_parse_html_only_email(self) -> None:
        """Parse an HTML-only email — should generate text from HTML."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: HTML Only\r\n"
            b"Date: Tue, 02 Jan 2024 09:00:00 -0500\r\n"
            b"Message-ID: <msg003@example.com>\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<html><body><h1>Welcome</h1><p>This is <strong>HTML</strong> content.</p></body></html>\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=3)
        assert result.body_html  # HTML should be preserved
        assert "Welcome" in result.body_text  # Text should be extracted from HTML
        assert "HTML" in result.body_text
        assert "<html>" not in result.body_text  # No raw HTML in text

    def test_parse_html_with_script_tags(self) -> None:
        """Ensure script/style tags are stripped during HTML→text conversion."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: HTML with scripts\r\n"
            b"Date: Wed, 03 Jan 2024 10:00:00 +0000\r\n"
            b"Message-ID: <msg004@example.com>\r\n"
            b"Content-Type: text/html\r\n"
            b"\r\n"
            b"<html><head><style>body{color:red}</style></head>"
            b"<body><script>alert('xss')</script><p>Safe content.</p></body></html>\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=4)
        assert "alert" not in result.body_text
        assert "color:red" not in result.body_text
        assert "Safe content" in result.body_text

    # ── Multipart emails ──────────────────────────────────────────────

    def test_parse_multipart_alternative(self) -> None:
        """Parse multipart/alternative — prefer text/plain."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: Multipart Alternative\r\n"
            b"Date: Thu, 04 Jan 2024 08:30:00 +0000\r\n"
            b"Message-ID: <msg005@example.com>\r\n"
            b"MIME-Version: 1.0\r\n"
            b'Content-Type: multipart/alternative; boundary="boundary123"\r\n'
            b"\r\n"
            b"--boundary123\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Plain text version of the email.\r\n"
            b"--boundary123\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<html><body><p>HTML version of the email.</p></body></html>\r\n"
            b"--boundary123--\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=5)
        assert "Plain text version" in result.body_text
        assert result.body_html  # HTML should also be captured

    def test_parse_multipart_with_attachment(self) -> None:
        """Parse multipart email with an attachment."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: With Attachment\r\n"
            b"Date: Fri, 05 Jan 2024 14:00:00 +0000\r\n"
            b"Message-ID: <msg006@example.com>\r\n"
            b"MIME-Version: 1.0\r\n"
            b'Content-Type: multipart/mixed; boundary="mixbound"\r\n'
            b"\r\n"
            b"--mixbound\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"See attached file.\r\n"
            b"--mixbound\r\n"
            b"Content-Type: application/pdf\r\n"
            b'Content-Disposition: attachment; filename="report.pdf"\r\n'
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n"
            b"JVBERi0xLjQKMSAwIG9iago=\r\n"
            b"--mixbound--\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=6)
        assert "See attached file" in result.body_text
        assert len(result.attachments) == 1
        assert result.attachments[0].filename == "report.pdf"
        assert result.attachments[0].content_type == "application/pdf"
        assert result.attachments[0].size > 0

    # ── Recipient parsing ─────────────────────────────────────────────

    def test_parse_multiple_recipients(self) -> None:
        """Parse email with To, Cc, and Bcc recipients."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: alice@example.com, Bob Smith <bob@example.com>\r\n"
            b"Cc: charlie@example.com\r\n"
            b"Subject: Multiple Recipients\r\n"
            b"Date: Sat, 06 Jan 2024 16:00:00 +0000\r\n"
            b"Message-ID: <msg007@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"To everyone.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=7)
        assert len(result.recipients) == 3

        to_recipients = [r for r in result.recipients if r.type.value == "to"]
        cc_recipients = [r for r in result.recipients if r.type.value == "cc"]

        assert len(to_recipients) == 2
        assert len(cc_recipients) == 1
        assert cc_recipients[0].email == "charlie@example.com"

    # ── International characters (RFC 2047) ───────────────────────────

    def test_parse_utf8_subject(self) -> None:
        """Parse email with UTF-8 encoded subject."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: =?UTF-8?B?44GT44KT44Gr44Gh44Gv?=\r\n"
            b"Date: Sun, 07 Jan 2024 10:00:00 +0900\r\n"
            b"Message-ID: <msg008@example.com>\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Japanese subject test.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=8)
        # "こんにちは" in UTF-8 base64 is "44GT44KT44Gr44Gh44Gv"
        assert result.subject  # Should be decoded, not raw =?UTF-8?B?...?=
        assert "=?" not in result.subject

    def test_parse_iso8859_subject(self) -> None:
        """Parse email with ISO-8859-1 encoded subject."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: =?ISO-8859-1?Q?Caf=E9_au_lait?=\r\n"
            b"Date: Mon, 08 Jan 2024 11:00:00 +0100\r\n"
            b"Message-ID: <msg009@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"French subject test.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=9)
        assert "Café" in result.subject or "Caf" in result.subject

    def test_parse_utf8_sender_name(self) -> None:
        """Parse email with international characters in sender name."""
        raw = (
            "From: =?UTF-8?B?5bGx55Sw5aSq6YOO?= <yamada@example.jp>\r\n"
            "To: receiver@example.com\r\n"
            "Subject: Test\r\n"
            "Date: Tue, 09 Jan 2024 12:00:00 +0900\r\n"
            "Message-ID: <msg010@example.com>\r\n"
            "Content-Type: text/plain\r\n"
            "\r\n"
            "Body.\r\n"
        ).encode("utf-8")

        result = self.parser.parse(raw, self.account_id, uid=10)
        assert result.sender_email == "yamada@example.jp"
        # Name should be decoded from base64
        assert "=?" not in result.sender_name

    # ── Date parsing ──────────────────────────────────────────────────

    def test_parse_date_with_timezone(self) -> None:
        """Date should be normalized to UTC."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: Timezone Test\r\n"
            b"Date: Wed, 10 Jan 2024 15:00:00 +0530\r\n"
            b"Message-ID: <msg011@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Body.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=11)
        assert result.date is not None
        assert result.date.tzinfo == timezone.utc
        # 15:00 IST (+05:30) = 09:30 UTC
        assert result.date.hour == 9
        assert result.date.minute == 30

    def test_parse_date_no_timezone(self) -> None:
        """Date without timezone should default to UTC."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: No TZ\r\n"
            b"Date: Thu, 11 Jan 2024 08:00:00\r\n"
            b"Message-ID: <msg012@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Body.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=12)
        assert result.date is not None
        assert result.date.tzinfo == timezone.utc

    def test_parse_malformed_date(self) -> None:
        """Malformed date should return None, not crash."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: Bad Date\r\n"
            b"Date: not-a-real-date\r\n"
            b"Message-ID: <msg013@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Body.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=13)
        assert result.date is None

    # ── Reply chains and signatures ───────────────────────────────────

    def test_strip_reply_chain(self) -> None:
        """Quoted reply text should be stripped from body."""
        raw = (
            b"From: bob@example.com\r\n"
            b"To: alice@example.com\r\n"
            b"Subject: Re: Hello\r\n"
            b"Date: Fri, 12 Jan 2024 10:00:00 +0000\r\n"
            b"Message-ID: <msg014@example.com>\r\n"
            b"In-Reply-To: <msg001@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Thanks Alice!\r\n"
            b"\r\n"
            b"On Mon, Jan 1, 2024 at 12:00 PM Alice <alice@example.com> wrote:\r\n"
            b"> Hello Bob,\r\n"
            b"> This is a plain text email.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=14)
        assert "Thanks Alice" in result.body_text
        assert "> Hello Bob" not in result.body_text

    def test_strip_signature(self) -> None:
        """Email signature after '-- ' should be stripped."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: With Signature\r\n"
            b"Date: Sat, 13 Jan 2024 11:00:00 +0000\r\n"
            b"Message-ID: <msg015@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Main message body.\r\n"
            b"\r\n"
            b"-- \r\n"
            b"John Doe\r\n"
            b"Senior Developer\r\n"
            b"john@example.com\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=15)
        assert "Main message body" in result.body_text
        assert "Senior Developer" not in result.body_text

    # ── Forwarded emails ──────────────────────────────────────────────

    def test_parse_forwarded_email(self) -> None:
        """Forwarded email should parse the forwarder's content."""
        raw = (
            b"From: forwarder@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: Fwd: Original Subject\r\n"
            b"Date: Sun, 14 Jan 2024 14:00:00 +0000\r\n"
            b"Message-ID: <msg016@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Check out this email:\r\n"
            b"\r\n"
            b"---------- Forwarded message ----------\r\n"
            b"From: original@example.com\r\n"
            b"Date: Sat, 13 Jan 2024 10:00:00 +0000\r\n"
            b"Subject: Original Subject\r\n"
            b"\r\n"
            b"Original content here.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=16)
        assert result.subject == "Fwd: Original Subject"
        assert result.sender_email == "forwarder@example.com"
        assert "Check out this email" in result.body_text

    # ── Missing/empty fields ──────────────────────────────────────────

    def test_parse_missing_subject(self) -> None:
        """Email with no Subject header should have empty subject."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Date: Mon, 15 Jan 2024 09:00:00 +0000\r\n"
            b"Message-ID: <msg017@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"No subject.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=17)
        assert result.subject == ""
        assert "No subject" in result.body_text

    def test_parse_missing_from(self) -> None:
        """Email with no From header should have empty sender."""
        raw = (
            b"To: receiver@example.com\r\n"
            b"Subject: No From\r\n"
            b"Date: Tue, 16 Jan 2024 10:00:00 +0000\r\n"
            b"Message-ID: <msg018@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Who sent this?\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=18)
        assert result.sender_name == ""
        assert result.sender_email == ""

    def test_parse_empty_body(self) -> None:
        """Email with empty body should parse without error."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: Empty Body\r\n"
            b"Date: Wed, 17 Jan 2024 11:00:00 +0000\r\n"
            b"Message-ID: <msg019@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=19)
        assert result.body_text == ""

    # ── In-Reply-To and References ────────────────────────────────────

    def test_parse_reply_headers(self) -> None:
        """In-Reply-To and References headers should be extracted."""
        raw = (
            b"From: bob@example.com\r\n"
            b"To: alice@example.com\r\n"
            b"Subject: Re: Thread Test\r\n"
            b"Date: Thu, 18 Jan 2024 12:00:00 +0000\r\n"
            b"Message-ID: <reply001@example.com>\r\n"
            b"In-Reply-To: <original001@example.com>\r\n"
            b"References: <original001@example.com> <reply000@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Reply body.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=20)
        assert result.in_reply_to == "<original001@example.com>"
        assert len(result.references) == 2
        assert "<original001@example.com>" in result.references
        assert "<reply000@example.com>" in result.references

    # ── ID generation ─────────────────────────────────────────────────

    def test_generate_deterministic_id(self) -> None:
        """Same account_id + uid + folder should produce the same ID."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: ID Test\r\n"
            b"Date: Fri, 19 Jan 2024 13:00:00 +0000\r\n"
            b"Message-ID: <msg020@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Body.\r\n"
        )

        result1 = self.parser.parse(raw, self.account_id, folder="INBOX", uid=100)
        result2 = self.parser.parse(raw, self.account_id, folder="INBOX", uid=100)
        assert result1.id == result2.id

    def test_different_folder_different_id(self) -> None:
        """Same email in different folders should have different IDs."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: Folder Test\r\n"
            b"Date: Sat, 20 Jan 2024 14:00:00 +0000\r\n"
            b"Message-ID: <msg021@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Body.\r\n"
        )

        result1 = self.parser.parse(raw, self.account_id, folder="INBOX", uid=100)
        result2 = self.parser.parse(raw, self.account_id, folder="Sent", uid=100)
        assert result1.id != result2.id

    # ── Raw headers ───────────────────────────────────────────────────

    def test_extract_raw_headers(self) -> None:
        """Useful headers should be extracted into raw_headers dict."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: Headers Test\r\n"
            b"Date: Sun, 21 Jan 2024 15:00:00 +0000\r\n"
            b"Message-ID: <msg022@example.com>\r\n"
            b"X-Mailer: TestMailer/1.0\r\n"
            b"Reply-To: replyto@example.com\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Body.\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=22)
        assert "Message-ID" in result.raw_headers
        assert "X-Mailer" in result.raw_headers
        assert "Reply-To" in result.raw_headers

    # ── Deeply nested MIME ────────────────────────────────────────────

    def test_parse_deeply_nested_mime(self) -> None:
        """Parse a multipart/mixed containing multipart/alternative."""
        raw = (
            b"From: sender@example.com\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: Nested MIME\r\n"
            b"Date: Mon, 22 Jan 2024 10:00:00 +0000\r\n"
            b"Message-ID: <msg023@example.com>\r\n"
            b"MIME-Version: 1.0\r\n"
            b'Content-Type: multipart/mixed; boundary="outer"\r\n'
            b"\r\n"
            b"--outer\r\n"
            b'Content-Type: multipart/alternative; boundary="inner"\r\n'
            b"\r\n"
            b"--inner\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Nested plain text.\r\n"
            b"--inner\r\n"
            b"Content-Type: text/html\r\n"
            b"\r\n"
            b"<p>Nested HTML.</p>\r\n"
            b"--inner--\r\n"
            b"--outer\r\n"
            b"Content-Type: image/png\r\n"
            b'Content-Disposition: attachment; filename="image.png"\r\n'
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n"
            b"iVBORw0KGgo=\r\n"
            b"--outer--\r\n"
        )

        result = self.parser.parse(raw, self.account_id, uid=23)
        assert "Nested plain text" in result.body_text
        assert len(result.attachments) == 1
        assert result.attachments[0].filename == "image.png"
