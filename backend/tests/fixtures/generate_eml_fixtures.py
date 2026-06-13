#!/usr/bin/env python3
"""Generate .eml test fixtures for EmailParser unit tests."""

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "eml"

FIXTURES: dict[str, bytes | str] = {
    "01_plain_text.eml": (
        b"From: Alice <alice@example.com>\r\n"
        b"To: Bob <bob@example.com>\r\n"
        b"Subject: Hello World\r\n"
        b"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
        b"Message-ID: <msg001@example.com>\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Hello Bob,\r\n\r\nThis is a plain text email.\r\n\r\nBest,\r\nAlice\r\n"
    ),
    "02_plain_no_name.eml": (
        b"From: alice@example.com\r\n"
        b"To: bob@example.com\r\n"
        b"Subject: No Name\r\n"
        b"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
        b"Message-ID: <msg002@example.com>\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\nBody text.\r\n"
    ),
    "03_html_only.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: HTML Only\r\n"
        b"Date: Tue, 02 Jan 2024 09:00:00 -0500\r\n"
        b"Message-ID: <msg003@example.com>\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b"<html><body><h1>Welcome</h1><p>This is <strong>HTML</strong> content.</p></body></html>\r\n"
    ),
    "04_html_with_scripts.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: HTML with scripts\r\n"
        b"Date: Wed, 03 Jan 2024 10:00:00 +0000\r\n"
        b"Message-ID: <msg004@example.com>\r\n"
        b"Content-Type: text/html\r\n"
        b"\r\n"
        b"<html><head><style>body{color:red}</style></head>"
        b"<body><script>alert('xss')</script><p>Safe content.</p></body></html>\r\n"
    ),
    "05_multipart_alternative.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: Multipart Alternative\r\n"
        b"Date: Thu, 04 Jan 2024 08:30:00 +0000\r\n"
        b"Message-ID: <msg005@example.com>\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/alternative; boundary="boundary123"\r\n'
        b"\r\n"
        b"--boundary123\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Plain text version of the email.\r\n"
        b"--boundary123\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        b"<html><body><p>HTML version of the email.</p></body></html>\r\n"
        b"--boundary123--\r\n"
    ),
    "06_multipart_attachment.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: With Attachment\r\n"
        b"Date: Fri, 05 Jan 2024 14:00:00 +0000\r\n"
        b"Message-ID: <msg006@example.com>\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="mixbound"\r\n'
        b"\r\n"
        b"--mixbound\r\n"
        b"Content-Type: text/plain\r\n\r\nSee attached file.\r\n"
        b"--mixbound\r\n"
        b"Content-Type: application/pdf\r\n"
        b'Content-Disposition: attachment; filename="report.pdf"\r\n'
        b"Content-Transfer-Encoding: base64\r\n\r\n"
        b"JVBERi0xLjQKMSAwIG9iago=\r\n"
        b"--mixbound--\r\n"
    ),
    "07_multiple_recipients.eml": (
        b"From: sender@example.com\r\n"
        b"To: alice@example.com, Bob Smith <bob@example.com>\r\n"
        b"Cc: charlie@example.com\r\n"
        b"Subject: Multiple Recipients\r\n"
        b"Date: Sat, 06 Jan 2024 16:00:00 +0000\r\n"
        b"Message-ID: <msg007@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\nTo everyone.\r\n"
    ),
    "08_utf8_subject.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: =?UTF-8?B?44GT44KT44Gr44Gh44Gv?=\r\n"
        b"Date: Sun, 07 Jan 2024 10:00:00 +0900\r\n"
        b"Message-ID: <msg008@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Japanese subject test.\r\n"
    ),
    "09_iso8859_subject.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: =?ISO-8859-1?Q?Caf=E9_au_lait?=\r\n"
        b"Date: Mon, 08 Jan 2024 11:00:00 +0100\r\n"
        b"Message-ID: <msg009@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\nFrench subject test.\r\n"
    ),
    "10_utf8_sender_name.eml": (
        "From: =?UTF-8?B?5bGx55Sw5aSq6YOO?= <yamada@example.jp>\r\n"
        "To: receiver@example.com\r\n"
        "Subject: Test\r\n"
        "Date: Tue, 09 Jan 2024 12:00:00 +0900\r\n"
        "Message-ID: <msg010@example.com>\r\n"
        "Content-Type: text/plain\r\n\r\nBody.\r\n"
    ),
    "11_date_timezone.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: Timezone Test\r\n"
        b"Date: Wed, 10 Jan 2024 15:00:00 +0530\r\n"
        b"Message-ID: <msg011@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\nBody.\r\n"
    ),
    "12_date_no_tz.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: No TZ\r\n"
        b"Date: Thu, 11 Jan 2024 08:00:00\r\n"
        b"Message-ID: <msg012@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\nBody.\r\n"
    ),
    "13_malformed_date.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: Bad Date\r\n"
        b"Date: not-a-real-date\r\n"
        b"Message-ID: <msg013@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\nBody.\r\n"
    ),
    "14_reply_chain.eml": (
        b"From: bob@example.com\r\n"
        b"To: alice@example.com\r\n"
        b"Subject: Re: Hello\r\n"
        b"Date: Fri, 12 Jan 2024 10:00:00 +0000\r\n"
        b"Message-ID: <msg014@example.com>\r\n"
        b"In-Reply-To: <msg001@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\n"
        b"Thanks Alice!\r\n\r\n"
        b"On Mon, Jan 1, 2024 at 12:00 PM Alice <alice@example.com> wrote:\r\n"
        b"> Hello Bob,\r\n> This is a plain text email.\r\n"
    ),
    "15_with_signature.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: With Signature\r\n"
        b"Date: Sat, 13 Jan 2024 11:00:00 +0000\r\n"
        b"Message-ID: <msg015@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\n"
        b"Main message body.\r\n\r\n-- \r\nJohn Doe\r\nSenior Developer\r\njohn@example.com\r\n"
    ),
    "16_forwarded.eml": (
        b"From: forwarder@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: Fwd: Original Subject\r\n"
        b"Date: Sun, 14 Jan 2024 14:00:00 +0000\r\n"
        b"Message-ID: <msg016@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\n"
        b"Check out this email:\r\n\r\n"
        b"---------- Forwarded message ----------\r\n"
        b"From: original@example.com\r\n"
        b"Date: Sat, 13 Jan 2024 10:00:00 +0000\r\n"
        b"Subject: Original Subject\r\n\r\nOriginal content here.\r\n"
    ),
    "17_missing_subject.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Date: Mon, 15 Jan 2024 09:00:00 +0000\r\n"
        b"Message-ID: <msg017@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\nNo subject.\r\n"
    ),
    "18_missing_from.eml": (
        b"To: receiver@example.com\r\n"
        b"Subject: No From\r\n"
        b"Date: Tue, 16 Jan 2024 10:00:00 +0000\r\n"
        b"Message-ID: <msg018@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\nWho sent this?\r\n"
    ),
    "19_empty_body.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: Empty Body\r\n"
        b"Date: Wed, 17 Jan 2024 11:00:00 +0000\r\n"
        b"Message-ID: <msg019@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\n"
    ),
    "20_reply_headers.eml": (
        b"From: bob@example.com\r\n"
        b"To: alice@example.com\r\n"
        b"Subject: Re: Thread Test\r\n"
        b"Date: Thu, 18 Jan 2024 12:00:00 +0000\r\n"
        b"Message-ID: <reply001@example.com>\r\n"
        b"In-Reply-To: <original001@example.com>\r\n"
        b"References: <original001@example.com> <reply000@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\nReply body.\r\n"
    ),
    "21_id_test.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: ID Test\r\n"
        b"Date: Fri, 19 Jan 2024 13:00:00 +0000\r\n"
        b"Message-ID: <msg020@example.com>\r\n"
        b"Content-Type: text/plain\r\n\r\nBody.\r\n"
    ),
    "22_raw_headers.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: Headers Test\r\n"
        b"Date: Sun, 21 Jan 2024 15:00:00 +0000\r\n"
        b"Message-ID: <msg022@example.com>\r\n"
        b"X-Mailer: TestMailer/1.0\r\n"
        b"Reply-To: replyto@example.com\r\n"
        b"Content-Type: text/plain\r\n\r\nBody.\r\n"
    ),
    "23_nested_mime.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: Nested MIME\r\n"
        b"Date: Mon, 22 Jan 2024 10:00:00 +0000\r\n"
        b"Message-ID: <msg023@example.com>\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="outer"\r\n'
        b"\r\n"
        b"--outer\r\n"
        b'Content-Type: multipart/alternative; boundary="inner"\r\n\r\n'
        b"--inner\r\n"
        b"Content-Type: text/plain\r\n\r\nNested plain text.\r\n"
        b"--inner\r\n"
        b"Content-Type: text/html\r\n\r\n<p>Nested HTML.</p>\r\n"
        b"--inner--\r\n"
        b"--outer\r\n"
        b"Content-Type: image/png\r\n"
        b'Content-Disposition: attachment; filename="image.png"\r\n'
        b"Content-Transfer-Encoding: base64\r\n\r\n"
        b"iVBORw0KGgo=\r\n"
        b"--outer--\r\n"
    ),
    "24_german_umlauts.eml": (
        b"From: =?UTF-8?Q?M=C3=BCller=2C_Hans?= <hans@example.de>\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: =?UTF-8?Q?Gr=C3=BC=C3=9Fe_aus_M=C3=BCnchen?=\r\n"
        b"Date: Tue, 23 Jan 2024 08:00:00 +0100\r\n"
        b"Message-ID: <msg024@example.de>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Guten Tag,\r\n\r\nSch=C3=B6ne Gr=C3=BC=C3=9Fe aus M=C3=BCnchen!\r\n"
    ),
    "25_base64_body.eml": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: Base64 Body\r\n"
        b"Date: Wed, 24 Jan 2024 09:00:00 +0000\r\n"
        b"Message-ID: <msg025@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"Content-Transfer-Encoding: base64\r\n\r\n"
        b"SGVsbG8gZnJvbSBiYXNlNjQh\r\n"
    ),
}


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in FIXTURES.items():
        path = FIXTURES_DIR / name
        data = content.encode("utf-8") if isinstance(content, str) else content
        path.write_bytes(data)
        print(f"Wrote {path.name}")
    print(f"\nGenerated {len(FIXTURES)} fixtures in {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
