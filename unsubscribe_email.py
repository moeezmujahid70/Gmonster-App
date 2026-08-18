"""Pure MIME-alternative footer composition for real campaign messages."""

from html import escape


FOOTER_TEXT = "Don't want to receive future emails from this sender?"


def compose_alternatives(plain_body: str, html_body: str, url: str, enabled: bool) -> tuple[str, str]:
    if not enabled:
        return plain_body, html_body
    if not url:
        raise ValueError("unsubscribe URL is required when footer is enabled")
    plain = plain_body.rstrip() + "\n\n{} Unsubscribe: {}".format(FOOTER_TEXT, url)
    footer = '<p>{} <a href="{}">Unsubscribe</a>.</p>'.format(FOOTER_TEXT, escape(url, quote=True))
    return plain, html_body.rstrip() + footer
