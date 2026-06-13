"""Unit tests for EmailParser using .eml fixture files."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest

from app.services.imap.parser import EmailParser

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "eml"


@pytest.fixture
def parser() -> EmailParser:
    return EmailParser()


@pytest.fixture
def account_id() -> str:
    return "test-account-123"


def load_fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


class TestEmailParserFixtures:
    """Parse real .eml files from tests/fixtures/eml/."""

    def test_all_fixtures_exist(self) -> None:
        """Ensure we have at least 20 .eml fixtures."""
        eml_files = list(FIXTURES_DIR.glob("*.eml"))
        assert len(eml_files) >= 20, f"Expected 20+ fixtures, found {len(eml_files)}"

    def test_all_fixtures_parse_without_error(
        self, parser: EmailParser, account_id: str
    ) -> None:
        """Every fixture should parse into a valid EmailMessage."""
        for path in sorted(FIXTURES_DIR.glob("*.eml")):
            raw = path.read_bytes()
            result = parser.parse(raw, account_id, folder="INBOX", uid=1)
            assert result.id, f"{path.name}: missing id"
            assert result.account_id == account_id, f"{path.name}: wrong account_id"

    def test_01_plain_text(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("01_plain_text.eml"), account_id, uid=1)
        assert result.subject == "Hello World"
        assert result.sender_email == "alice@example.com"
        assert "Hello Bob" in result.body_text

    def test_03_html_only(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("03_html_only.eml"), account_id, uid=3)
        assert result.body_html
        assert "Welcome" in result.body_text
        assert "<html>" not in result.body_text

    def test_05_multipart_alternative(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("05_multipart_alternative.eml"), account_id, uid=5)
        assert "Plain text version" in result.body_text
        assert result.body_html

    def test_06_attachment(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("06_multipart_attachment.eml"), account_id, uid=6)
        assert len(result.attachments) == 1
        assert result.attachments[0].filename == "report.pdf"

    def test_08_utf8_subject(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("08_utf8_subject.eml"), account_id, uid=8)
        assert "=?" not in result.subject
        assert result.subject  # decoded Japanese

    def test_09_iso8859_subject(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("09_iso8859_subject.eml"), account_id, uid=9)
        assert "Café" in result.subject or "Caf" in result.subject

    def test_11_date_timezone(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("11_date_timezone.eml"), account_id, uid=11)
        assert result.date is not None
        assert result.date.tzinfo == UTC
        assert result.date.hour == 9
        assert result.date.minute == 30

    def test_14_reply_chain_stripped(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("14_reply_chain.eml"), account_id, uid=14)
        assert "Thanks Alice" in result.body_text
        assert "> Hello Bob" not in result.body_text

    def test_15_signature_stripped(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("15_with_signature.eml"), account_id, uid=15)
        assert "Main message body" in result.body_text
        assert "Senior Developer" not in result.body_text

    def test_16_forwarded(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("16_forwarded.eml"), account_id, uid=16)
        assert result.subject == "Fwd: Original Subject"
        assert "Check out this email" in result.body_text

    def test_20_reply_headers(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("20_reply_headers.eml"), account_id, uid=20)
        assert result.in_reply_to == "<original001@example.com>"
        assert len(result.references) == 2

    def test_23_nested_mime(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("23_nested_mime.eml"), account_id, uid=23)
        assert "Nested plain text" in result.body_text
        assert result.attachments[0].filename == "image.png"

    def test_24_german_umlauts(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("24_german_umlauts.eml"), account_id, uid=24)
        assert "München" in result.subject or "Gr" in result.subject
        assert result.sender_email == "hans@example.de"

    def test_25_base64_body(self, parser: EmailParser, account_id: str) -> None:
        result = parser.parse(load_fixture("25_base64_body.eml"), account_id, uid=25)
        assert "Hello from base64" in result.body_text

    def test_deterministic_id_from_fixture(self, parser: EmailParser, account_id: str) -> None:
        raw = load_fixture("21_id_test.eml")
        r1 = parser.parse(raw, account_id, folder="INBOX", uid=100)
        r2 = parser.parse(raw, account_id, folder="INBOX", uid=100)
        assert r1.id == r2.id
        r3 = parser.parse(raw, account_id, folder="Sent", uid=100)
        assert r1.id != r3.id
