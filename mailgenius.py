"""MailGenius audit requests through the authenticated GMonster server."""

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
import logging
from urllib.parse import quote, urlparse

import requests


logger = logging.getLogger("gmonster.mailgenius")


def _server_request(method, path):
    """Import the authenticated desktop request helper only when it is used."""
    from gmonster_api import authenticated_request

    return authenticated_request(method, path)


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


class MailGeniusError(RuntimeError):
    """Raised when MailGenius cannot start or return an audit."""

    def __init__(self, message, code="MAILGENIUS_FAILED"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MailGeniusAudit:
    audit_id: str
    test_email: str


@dataclass(frozen=True)
class MailGeniusResult:
    status: str
    pending: bool
    data: dict = field(default_factory=dict)


class MailGeniusClient:
    def start_audit(self):
        """Create a server-owned audit and return its visible test address."""
        data = self._request("POST", "verify/mailgenius/audits", 201)
        audit_id = data.get("audit_id")
        test_email = data.get("test_email")

        if not isinstance(audit_id, str) or not audit_id.strip():
            raise MailGeniusError("MailGenius returned an invalid audit.")
        if not isinstance(test_email, str) or "@" not in test_email:
            raise MailGeniusError("MailGenius returned an invalid audit address.")
        logger.info("MailGenius: server audit created")
        return MailGeniusAudit(audit_id=audit_id.strip(), test_email=test_email)

    def _request(self, method, path, expected_status):
        try:
            response = _server_request(method, path)
        except requests.RequestException as exc:
            logger.error("MailGenius server request failed: %s", exc)
            raise MailGeniusError(
                "Could not reach the MailGenius service. Please try again.",
                "MAILGENIUS_CONNECTION",
            ) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise MailGeniusError("MailGenius returned an invalid response.") from exc

        if not isinstance(data, dict):
            raise MailGeniusError("MailGenius returned an invalid response.")
        if response.status_code != expected_status:
            raise MailGeniusError(
                self._error_message(data, response.status_code),
                str(data.get("error") or "MAILGENIUS_FAILED").upper(),
            )
        return data

    @staticmethod
    def _error_message(data, status_code):
        error = str(data.get("error") or "")
        messages = {
            "daily_audit_limit_reached": "Daily MailGenius audit limit reached. Please try again tomorrow.",
            "mailgenius_unconfigured": "MailGenius is not configured on the server.",
            "mailgenius_timeout": "MailGenius analysis timed out. Please try again shortly.",
            "mailgenius_connection_error": "Could not reach the MailGenius service. Please try again.",
            "audit_not_found": "MailGenius audit was not found.",
            "audit_not_ready": "MailGenius audit is still being created. Please try again shortly.",
        }
        if error in messages:
            return messages[error]
        if status_code == 401:
            return "Please sign in again before running a MailGenius audit."
        if status_code in {402, 403}:
            return "An active subscription is required for MailGenius audits."
        return "MailGenius could not complete the check. Please try again."

    def get_result(self, audit_id):
        data = self._request(
            "GET",
            "verify/mailgenius/audits/{}".format(quote(str(audit_id), safe="")),
            200,
        )
        status = str(data.get("status", "unknown")).lower()
        result = MailGeniusResult(
            status=status,
            pending=status in {"pending", "processing", "queued", "not_ready"},
            data=data,
        )
        logger.info("MailGenius: server audit status=%s", result.status)
        return result

    def wait_for_result(self, audit_id, attempts=50, interval_seconds=3, sleep=None):
        if sleep is None:
            import time
            sleep = time.sleep
        for _ in range(attempts):
            result = self.get_result(audit_id)
            if not result.pending:
                return result
            sleep(interval_seconds)
        raise MailGeniusError("MailGenius analysis timed out. Please try again.")
