"""MailGenius audit requests through the RapidAPI gateway."""

from dataclasses import dataclass, field
import logging

import requests


logger = logging.getLogger("gmonster.mailgenius")


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
