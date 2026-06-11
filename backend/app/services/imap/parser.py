"""Email parser — converts raw email bytes into structured EmailMessage objects.

Handles:
- MIME multipart (text/plain preferred, HTML→text fallback via html2text)
- RFC 2047 encoded headers (international characters)
- Timezone normalization to UTC
- Reply chain / signature stripping
- Attachment metadata extraction
- Deterministic ID generation via sha256
"""

from __future__ import annotations

import email
import email.header
import email.policy
import email.utils
import hashlib
import logging
import re
from datetime import datetime, timezone
from email.message import Message

import html2text
from bs4 import BeautifulSoup

from app.schemas.email import Attachment, EmailMessage, Recipient, RecipientType

logger = logging.getLogger(__name__)


class EmailParser:
    """Parse raw email bytes into structured EmailMessage objects."""

    def __init__(self) -> None:
        self._html_converter = html2text.HTML2Text()
        self._html_converter.ignore_links = False
        self._html_converter.ignore_images = True
        self._html_converter.ignore_emphasis = False
        self._html_converter.body_width = 0  # Don't wrap lines

    def parse(
        self,
        raw_bytes: bytes,
        account_id: str,
        folder: str = "INBOX",
        uid: int = 0,
    ) -> EmailMessage:
        """Parse raw email bytes into an EmailMessage.

        Args:
            raw_bytes: Raw email content (RFC 822 format).
            account_id: ID of the account this email belongs to.
            folder: IMAP folder the email was fetched from.
            uid: IMAP UID of the email.

        Returns:
            Parsed EmailMessage with all fields populated.
        """
        msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

        message_id = msg.get("Message-ID", "") or ""
        message_id = message_id.strip()

        subject = self._decode_header(msg.get("Subject", "") or "")
        sender_name, sender_email = self._parse_sender(msg)
        recipients = self._extract_recipients(msg)
        date = self._parse_date(msg.get("Date", "") or "")
        body_text, body_html = self._extract_body(msg)
        attachments = self._extract_attachments(msg)
        raw_headers = self._extract_raw_headers(msg)
        in_reply_to = (msg.get("In-Reply-To", "") or "").strip()
        references = self._parse_references(msg.get("References", "") or "")
        flags_raw = msg.get("X-FLAGS", "") or ""
        flags = [f.strip() for f in flags_raw.split(",") if f.strip()]

        email_id = self._generate_id(account_id, uid, folder)

        parsed = EmailMessage(
            id=email_id,
            account_id=account_id,
            message_id=message_id,
            subject=subject,
            sender_name=sender_name,
            sender_email=sender_email,
            recipients=recipients,
            date=date,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments,
            raw_headers=raw_headers,
            folder=folder,
            flags=flags,
            uid=uid,
            in_reply_to=in_reply_to,
            references=references,
        )

        logger.debug(
            "Parsed email uid=%d subject='%s' from=%s attachments=%d",
            uid,
            subject[:50],
            sender_email,
            len(attachments),
        )

        return parsed

    def _extract_body(self, msg: Message) -> tuple[str, str]:
        """Extract text and HTML body from a MIME message.

        Preference order:
        1. text/plain part → body_text
        2. text/html part → body_html, converted to body_text via html2text
        """
        body_text = ""
        body_html = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in disposition:
                    continue

                if content_type == "text/plain" and not body_text:
                    payload = part.get_content()
                    if isinstance(payload, str):
                        body_text = payload
                    elif isinstance(payload, bytes):
                        body_text = payload.decode("utf-8", errors="replace")

                elif content_type == "text/html" and not body_html:
                    payload = part.get_content()
                    if isinstance(payload, str):
                        body_html = payload
                    elif isinstance(payload, bytes):
                        body_html = payload.decode("utf-8", errors="replace")
        else:
            content_type = msg.get_content_type()
            payload = msg.get_content()

            if isinstance(payload, bytes):
                payload = payload.decode("utf-8", errors="replace")

            if isinstance(payload, str):
                if content_type == "text/html":
                    body_html = payload
                else:
                    body_text = payload

        # If we have HTML but no plain text, convert HTML to text
        if body_html and not body_text:
            body_text = self._html_to_text(body_html)

        # Clean up the text body
        body_text = self._clean_text(body_text)

        return body_text, body_html

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text using html2text.

        Uses BeautifulSoup to sanitize first, then html2text for conversion.
        """
        try:
            # Sanitize HTML with BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            # Remove script/style tags
            for tag in soup(["script", "style"]):
                tag.decompose()
            clean_html = str(soup)
            return self._html_converter.handle(clean_html).strip()
        except Exception:
            logger.warning("Failed to convert HTML to text, falling back to raw strip")
            return BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()

    def _parse_sender(self, msg: Message) -> tuple[str, str]:
        """Extract sender name and email from the From header."""
        from_header = msg.get("From", "") or ""
        from_header = self._decode_header(from_header)

        if not from_header:
            return "", ""

        # email.utils.parseaddr handles "Name <email>" and bare email
        name, addr = email.utils.parseaddr(from_header)
        return name.strip(), addr.strip().lower()

    def _extract_recipients(self, msg: Message) -> list[Recipient]:
        """Extract all recipients (To, Cc, Bcc) from headers."""
        recipients: list[Recipient] = []

        header_type_map = {
            "To": RecipientType.TO,
            "Cc": RecipientType.CC,
            "Bcc": RecipientType.BCC,
        }

        for header_name, recipient_type in header_type_map.items():
            raw = msg.get(header_name, "") or ""
            raw = self._decode_header(raw)

            if not raw:
                continue

            # getaddresses handles comma-separated lists and quoted names
            addresses = email.utils.getaddresses([raw])
            for name, addr in addresses:
                if addr:  # Skip empty addresses
                    recipients.append(
                        Recipient(
                            name=name.strip(),
                            email=addr.strip().lower(),
                            type=recipient_type,
                        )
                    )

        return recipients

    def _decode_header(self, raw: str) -> str:
        """Decode RFC 2047 encoded header values.

        Handles international characters like:
        =?UTF-8?B?...?= and =?ISO-8859-1?Q?...?=
        """
        if not raw:
            return ""

        try:
            # If it's already a properly decoded string (email.policy.default does this),
            # just return it
            if "=?" not in raw:
                return raw.strip()

            decoded_parts = email.header.decode_header(raw)
            result_parts: list[str] = []

            for content, charset in decoded_parts:
                if isinstance(content, bytes):
                    encoding = charset or "utf-8"
                    try:
                        result_parts.append(content.decode(encoding))
                    except (UnicodeDecodeError, LookupError):
                        result_parts.append(content.decode("utf-8", errors="replace"))
                else:
                    result_parts.append(content)

            return " ".join(result_parts).strip()
        except Exception:
            logger.warning("Failed to decode header: %s", raw[:100])
            return raw.strip()

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse email date string and normalize to UTC.

        Handles various date formats including malformed ones.
        """
        if not date_str:
            return None

        try:
            dt = email.utils.parsedate_to_datetime(date_str)
            # Normalize to UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            logger.warning("Failed to parse date: %s", date_str[:50])
            return None

    def _extract_attachments(self, msg: Message) -> list[Attachment]:
        """Extract attachment metadata (filename, type, size) without content."""
        attachments: list[Attachment] = []

        if not msg.is_multipart():
            return attachments

        for part in msg.walk():
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" not in disposition and "inline" not in disposition:
                continue

            # Skip text parts that are inline (body content)
            content_type = part.get_content_type()
            if content_type in ("text/plain", "text/html") and "attachment" not in disposition:
                continue

            filename = part.get_filename() or ""
            if filename:
                filename = self._decode_header(filename)

            # Estimate size from payload
            payload = part.get_payload(decode=True)
            size = len(payload) if payload else 0

            attachments.append(
                Attachment(
                    filename=filename,
                    content_type=content_type,
                    size=size,
                )
            )

        return attachments

    def _extract_raw_headers(self, msg: Message) -> dict[str, str]:
        """Extract a subset of useful raw headers as a dict."""
        useful_headers = [
            "From",
            "To",
            "Cc",
            "Bcc",
            "Subject",
            "Date",
            "Message-ID",
            "In-Reply-To",
            "References",
            "Reply-To",
            "Content-Type",
            "MIME-Version",
            "X-Mailer",
            "List-Unsubscribe",
        ]

        headers: dict[str, str] = {}
        for header in useful_headers:
            value = msg.get(header)
            if value:
                headers[header] = str(value).strip()

        return headers

    def _parse_references(self, references_str: str) -> list[str]:
        """Parse the References header into a list of Message-IDs."""
        if not references_str:
            return []

        # References header contains space-separated Message-IDs
        # Each is wrapped in angle brackets: <id@domain>
        refs = re.findall(r"<[^>]+>", references_str)
        return [r.strip() for r in refs if r.strip()]

    def _clean_text(self, text: str) -> str:
        """Clean up email body text.

        - Strip reply chains (quoted text)
        - Remove email signatures
        - Collapse excessive whitespace
        """
        if not text:
            return ""

        text = self._strip_reply_chains(text)
        text = self._strip_signature(text)

        # Collapse multiple blank lines into at most two
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Strip trailing whitespace from each line
        text = "\n".join(line.rstrip() for line in text.split("\n"))

        return text.strip()

    def _strip_reply_chains(self, text: str) -> str:
        """Remove quoted reply chains from email body.

        Detects patterns like:
        - "On Mon, Jan 1, 2024 at 12:00 PM Name <email> wrote:"
        - Lines starting with ">"
        - "---------- Forwarded message ----------"
        """
        lines = text.split("\n")
        result: list[str] = []
        in_quote = False

        for line in lines:
            stripped = line.strip()

            # Detect start of a reply chain
            if re.match(
                r"^On\s+.+\s+wrote:\s*$",
                stripped,
                re.IGNORECASE,
            ):
                in_quote = True
                continue

            # Forwarded message separator
            if re.match(r"^-{5,}\s*Forwarded message\s*-{5,}$", stripped, re.IGNORECASE):
                in_quote = True
                continue

            # Quoted lines
            if stripped.startswith(">"):
                in_quote = True
                continue

            # If we hit a non-quoted line after quotes, stop stripping
            if in_quote and stripped:
                in_quote = False

            if not in_quote:
                result.append(line)

        return "\n".join(result)

    def _strip_signature(self, text: str) -> str:
        """Remove email signature after the conventional '-- ' delimiter."""
        # The standard signature delimiter is "-- " (dash-dash-space)
        parts = text.split("\n-- \n", 1)
        if len(parts) > 1:
            return parts[0]
        return text

    @staticmethod
    def _generate_id(account_id: str, uid: int, folder: str) -> str:
        """Generate a deterministic email ID using sha256.

        This ensures uniqueness across accounts and prevents duplicate indexing.
        Using Message-ID alone is unreliable as it's not guaranteed unique.
        """
        key = f"{account_id}:{uid}:{folder}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()
