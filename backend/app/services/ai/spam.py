"""Spam and phishing detection service."""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.services.ai.client import OllamaClient
from app.services.ai.prompts import PromptRegistry
from app.services.ai.schemas import HeaderSignal, LLMSpamSignal, SpamDetectionResult, URLSignal
from app.services.ai.utils import clean_whitespace, parse_json_object, response_content

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s<>'\")]+", re.IGNORECASE)
SHORTENER_DOMAINS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "is.gd",
    "ow.ly",
    "buff.ly",
}
SUSPICIOUS_TERMS = {
    "login",
    "verify",
    "secure",
    "account",
    "update",
    "password",
    "wallet",
    "bank",
    "billing",
}
SUSPICIOUS_TLDS = {".zip", ".mov", ".top", ".xyz", ".tk", ".ru", ".cn"}


class SpamDetectionService:
    """Combine URL, header, and LLM spam signals."""

    URL_WEIGHT = 0.35
    HEADER_WEIGHT = 0.25
    LLM_WEIGHT = 0.40

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        timeout: float | None = None,
        prompt_registry: type[PromptRegistry] = PromptRegistry,
    ) -> None:
        self.client = client or OllamaClient()
        self.model = model or settings.OLLAMA_FAST_MODEL
        self.timeout = timeout or float(settings.OLLAMA_FAST_TIMEOUT)
        self.prompt_registry = prompt_registry

    async def analyze_email(
        self,
        subject: str,
        sender: str,
        body: str,
        raw_headers: dict[str, str] | str | None = None,
    ) -> SpamDetectionResult:
        """Analyze spam/phishing risk with weighted signals."""
        urls = self._analyze_urls(body)
        url_score = max((signal.risk_score for signal in urls), default=0.0)
        header_signal = self._analyze_headers(raw_headers)
        llm_signal = await self._llm_signal(subject, sender, body)

        if llm_signal is None:
            combined = (
                url_score * self.URL_WEIGHT + header_signal.risk_score * self.HEADER_WEIGHT
            ) / (self.URL_WEIGHT + self.HEADER_WEIGHT)
            confidence = 0.45
            llm_score = 0.0
            is_phishing = combined >= 0.75
        else:
            llm_score = llm_signal.spam_score
            combined = (
                url_score * self.URL_WEIGHT
                + header_signal.risk_score * self.HEADER_WEIGHT
                + llm_score * self.LLM_WEIGHT
            )
            confidence = min(1.0, (llm_signal.confidence + 0.75) / 2)
            is_phishing = llm_signal.is_phishing or combined >= 0.75

        return SpamDetectionResult(
            url_score=round(min(1.0, url_score), 4),
            header_score=round(min(1.0, header_signal.risk_score), 4),
            llm_score=round(min(1.0, llm_score), 4),
            combined_score=round(min(1.0, combined), 4),
            is_spam=combined >= 0.65 or is_phishing,
            is_phishing=is_phishing,
            confidence=round(confidence, 4),
            urls=urls,
            header_signal=header_signal,
            llm_signal=llm_signal,
        )

    def _analyze_urls(self, body: str) -> list[URLSignal]:
        signals: list[URLSignal] = []
        for url in URL_RE.findall(body):
            parsed = urlparse(url)
            domain = (parsed.hostname or "").lower()
            reasons: list[str] = []
            score = 0.0

            if not domain:
                score += 0.2
                reasons.append("missing_domain")
            if parsed.scheme == "http":
                score += 0.15
                reasons.append("plain_http")
            if "@" in url:
                score += 0.25
                reasons.append("userinfo_in_url")
            if domain.startswith("xn--"):
                score += 0.25
                reasons.append("punycode_domain")
            if domain in SHORTENER_DOMAINS:
                score += 0.25
                reasons.append("url_shortener")
            if any(domain.endswith(tld) for tld in SUSPICIOUS_TLDS):
                score += 0.2
                reasons.append("suspicious_tld")
            if sum(1 for part in domain.split(".") if part) >= 4:
                score += 0.15
                reasons.append("many_subdomains")
            if "-" in domain and len(domain) > 20:
                score += 0.15
                reasons.append("long_hyphenated_domain")
            if any(term in domain or term in parsed.path.lower() for term in SUSPICIOUS_TERMS):
                score += 0.2
                reasons.append("credential_or_account_terms")
            try:
                ipaddress.ip_address(domain)
            except ValueError:
                pass
            else:
                score += 0.25
                reasons.append("ip_address_domain")

            signals.append(
                URLSignal(
                    url=url,
                    domain=domain,
                    risk_score=round(min(1.0, score), 4),
                    reasons=reasons,
                )
            )
        return signals

    def _analyze_headers(self, raw_headers: dict[str, str] | str | None) -> HeaderSignal:
        header_text = self._headers_to_text(raw_headers)
        reasons: list[str] = []
        spf = self._auth_passed(header_text, "spf")
        dkim = self._auth_passed(header_text, "dkim")
        dmarc = self._auth_passed(header_text, "dmarc")
        score = 0.0

        for name, passed in (("spf", spf), ("dkim", dkim), ("dmarc", dmarc)):
            if passed is False:
                score += 0.3
                reasons.append(f"{name}_failed")
            elif passed is None:
                score += 0.1
                reasons.append(f"{name}_missing")

        return HeaderSignal(
            spf_pass=spf,
            dkim_pass=dkim,
            dmarc_pass=dmarc,
            risk_score=round(min(1.0, score), 4),
            reasons=reasons,
        )

    async def _llm_signal(self, subject: str, sender: str, body: str) -> LLMSpamSignal | None:
        prompt = self.prompt_registry.get(PromptRegistry.SPAM_V1)
        user_prompt = prompt.render(
            subject=clean_whitespace(subject),
            sender=clean_whitespace(sender),
            body=clean_whitespace(body)[:2000],
        )
        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=self.timeout,
                format="json",
                options={"temperature": 0},
            )
            return LLMSpamSignal.model_validate(parse_json_object(response_content(response)))
        except Exception:
            logger.warning("LLM spam classification failed; using heuristic-only score", exc_info=True)
            return None

    @staticmethod
    def _headers_to_text(raw_headers: dict[str, str] | str | None) -> str:
        if raw_headers is None:
            return ""
        if isinstance(raw_headers, str):
            return raw_headers.lower()
        return "\n".join(f"{key}: {value}" for key, value in raw_headers.items()).lower()

    @staticmethod
    def _auth_passed(header_text: str, mechanism: str) -> bool | None:
        if f"{mechanism}=pass" in header_text:
            return True
        if (
            f"{mechanism}=fail" in header_text
            or f"{mechanism}=softfail" in header_text
            or f"{mechanism}=temperror" in header_text
            or f"{mechanism}=permerror" in header_text
        ):
            return False
        return None
