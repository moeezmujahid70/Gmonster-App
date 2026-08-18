"""MailGenius audit requests through the RapidAPI gateway."""

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
import logging
from urllib.parse import urlparse

import requests


logger = logging.getLogger("gmonster.mailgenius")


class _MailGeniusHTMLSanitizer(HTMLParser):
    """Keep the small rich-text subset supported by the audit details panel."""

    allowed_tags = {"a", "b", "br", "code", "div", "em", "i", "li", "ol", "p", "strong", "u", "ul"}
    blocked_tags = {"script", "style"}
    allowed_link_schemes = {"http", "https", "mailto"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.open_tags = []
        self.blocked_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.blocked_tags:
            self.blocked_depth += 1
            return
        if self.blocked_depth or tag not in self.allowed_tags:
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        if tag == "a":
            href = next((value for name, value in attrs if name.lower() == "href"), "")
            parsed_href = urlparse(href or "")
            if parsed_href.scheme.lower() not in self.allowed_link_schemes:
                return
            self.parts.append('<a href="{}">'.format(escape(href, quote=True)))
            self.open_tags.append(tag)
            return
        self.parts.append("<{}>".format(tag))
        self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br" and not self.blocked_depth:
            self.parts.append("<br>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.blocked_tags:
            self.blocked_depth = max(0, self.blocked_depth - 1)
            return
        if self.blocked_depth or tag not in self.allowed_tags or tag == "br":
            return
        if tag in self.open_tags:
            while self.open_tags:
                open_tag = self.open_tags.pop()
                self.parts.append("</{}>".format(open_tag))
                if open_tag == tag:
                    break

    def handle_data(self, data):
        if not self.blocked_depth:
            self.parts.append(escape(data))

    def rendered_html(self):
        while self.open_tags:
            self.parts.append("</{}>".format(self.open_tags.pop()))
        return "".join(self.parts)


def sanitize_mailgenius_html(value):
    """Return safe rich text from the MailGenius API for a QTextBrowser."""
    sanitizer = _MailGeniusHTMLSanitizer()
    sanitizer.feed(str(value))
    sanitizer.close()
    return sanitizer.rendered_html()


class MailGeniusError(Exception):
    """Raised when MailGenius cannot start or return an audit."""


@dataclass(frozen=True)
class MailGeniusAudit:
    slug: str
    test_email: str


@dataclass(frozen=True)
class MailGeniusResult:
    status: str
    pending: bool
    data: dict = field(default_factory=dict)


class MailGeniusClient:
    def __init__(self, config, session=requests, timeout=(5, 20)):
        self.key = str(config.get("rapidapi_key", "")).strip()
        self.host = str(config.get("rapidapi_host", "")).strip()
        self.session = session
        self.timeout = timeout
        if not self.key or not self.host:
            raise MailGeniusError("MailGenius is not configured.")

    def start_audit(self):
        logger.info("MailGenius: requesting audit address from %s", self.host)
        data = self._get("/external/api/email-audit")
        slug = data.get("slug")
        test_email = data.get("test_email")
        if isinstance(test_email, str) and "@" in test_email and not slug:
            slug = test_email.split("@", 1)[0]
            if slug.startswith("test-"):
                slug = slug[len("test-"):]
        if not isinstance(slug, str) or not isinstance(test_email, str):
            logger.error("MailGenius: audit response omitted test_email")
            raise MailGeniusError("MailGenius did not return an audit address.")
        logger.info("MailGenius: audit address created (slug=%s)", slug)
        return MailGeniusAudit(slug=slug, test_email=test_email)

    def _get(self, path):
        try:
            response = self.session.get(
                "https://{}{}".format(self.host, path),
                headers={
                    "x-rapidapi-key": self.key,
                    "x-rapidapi-host": self.host,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.error("MailGenius: request failed for %s: %s", path, exc)
            raise MailGeniusError("MailGenius connection failed. Please try again.") from exc
        if response.status_code >= 400:
            logger.error("MailGenius: request for %s returned HTTP %s", path, response.status_code)
            raise MailGeniusError(
                "MailGenius request failed ({}).".format(response.status_code)
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise MailGeniusError("MailGenius returned an invalid response.") from exc

        if not isinstance(data, dict):
            raise MailGeniusError("MailGenius returned an invalid response.")
        return data

    def get_result(self, slug):
        data = self._get("/external/api/email-result/{}".format(slug))
        status = str(data.get("status", "unknown")).lower()
        result = MailGeniusResult(
            status=status,
            pending=status in {"pending", "processing", "queued", "not_ready"},
            data=data,
        )
        logger.info("MailGenius: audit %s status=%s", slug, result.status)
        return result

    def wait_for_result(self, slug, attempts=20, interval_seconds=3, sleep=None):
        if sleep is None:
            import time
            sleep = time.sleep
        for _ in range(attempts):
            result = self.get_result(slug)
            if not result.pending:
                return result
            sleep(interval_seconds)
        raise MailGeniusError("MailGenius analysis timed out. Please try again.")
