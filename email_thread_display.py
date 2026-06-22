import html
import re
from collections.abc import Mapping

from bs4 import BeautifulSoup


QUOTE_CLASS_PATTERNS = (
    "gmail_quote",
    "gmail_attr",
    "yahoo_quoted",
    "moz-cite-prefix",
    "protonmail_quote",
    "zmail_extra",
    "OutlookMessageHeader",
)


def body_to_thread_html(row_data: Mapping) -> str:
    body = str(row_data.get("body", "") or "")
    if _is_sent_message(row_data):
        return _render_body_html(body)
    return _render_body_html(_strip_quoted_history(body))


def message_to_thread_html(row_data: Mapping, show_metadata=False) -> str:
    body_html = body_to_thread_html(row_data)
    if show_metadata:
        separator_text = _separator_text(row_data)
        return (
            '<div style="margin:34px 0 26px 0; padding:0; line-height:1.55;">'
            '<table width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 22px 0;">'
            "<tr>"
            '<td><hr style="border:0; border-top:1px solid #d8dee8;"></td>'
            '<td width="220" align="center" style="color:#667085; font-size:12px; '
            f'font-weight:600; white-space:nowrap;">{separator_text}</td>'
            '<td><hr style="border:0; border-top:1px solid #d8dee8;"></td>'
            "</tr>"
            "</table>"
            f"{body_html}"
            "</div>"
        )
    return (
        '<div style="margin:0 0 30px 0; padding:0 0 22px 0; line-height:1.55;">'
        f"{body_html}"
        "</div>"
    )


def header_date_text(row_data: Mapping) -> str:
    value = row_data.get("date", "")
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def _separator_text(row_data):
    label = "Original email" if _is_sent_message(row_data) else "Previous reply"
    date_text = header_date_text(row_data)
    if date_text:
        return html.escape(f"{label} - {date_text}")
    return html.escape(label)


def _is_sent_message(row_data):
    value = row_data.get("is_sent", False)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "sent")
    return bool(value)


def _strip_quoted_history(body):
    if _looks_like_html(body):
        return _strip_html_quoted_history(body)
    return _strip_plain_quoted_history(body)


def _render_body_html(body):
    if _looks_like_html(body):
        return _sanitize_html_body(body)
    return html.escape(body).replace("\n", "<br>")


def _looks_like_html(body):
    text = str(body or "")
    return bool(re.search(r"</?(html|body|div|p|br|blockquote|span|table)\b", text, re.I))


def _strip_html_quoted_history(body):
    soup = BeautifulSoup(body, "html.parser")
    _remove_unsafe_html(soup)

    for tag in list(soup.find_all(["blockquote"])):
        tag.decompose()

    for tag in list(soup.find_all(True)):
        classes = " ".join(tag.get("class", []))
        tag_id = str(tag.get("id", "") or "")
        combined = f"{classes} {tag_id}"
        if _is_quote_container(combined):
            tag.decompose()

    text_after_html_cleanup = _sanitize_html_body(str(soup))
    text_after_html_cleanup = _strip_plain_quoted_history(text_after_html_cleanup)
    return text_after_html_cleanup


def _sanitize_html_body(body):
    soup = BeautifulSoup(body, "html.parser")
    _remove_unsafe_html(soup)
    body_tag = soup.find("body")
    if body_tag:
        return "".join(str(child) for child in body_tag.contents).strip()
    return str(soup).strip()


def _remove_unsafe_html(soup):
    for tag in list(soup.find_all(["script", "style", "meta", "link"])):
        tag.decompose()
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag.attrs[attr]


def _is_quote_container(value):
    lowered = str(value or "").lower()
    return any(pattern.lower() in lowered for pattern in QUOTE_CLASS_PATTERNS)


def _strip_plain_quoted_history(body):
    text = _html_to_plain_text_if_needed(str(body or ""))
    lines = text.splitlines()
    kept = []

    for index, line in enumerate(lines):
        if _is_plain_quote_start(lines, index):
            break
        kept.append(line)

    return "\n".join(kept).strip()


def _html_to_plain_text_if_needed(text):
    if not _looks_like_html(text):
        return text
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text("\n")


def _is_plain_quote_start(lines, index):
    line = str(lines[index] or "").strip()
    lowered = line.lower()
    if not line:
        return False
    if re.match(r"^on .{1,240}wrote:\s*$", lowered):
        return True
    if "ezt írta" in lowered or " ezt irta" in lowered:
        return True
    if lowered.startswith("-----original message-----"):
        return True
    if _starts_outlook_header_block(lines, index):
        return True
    return False


def _starts_outlook_header_block(lines, index):
    current = str(lines[index] or "").strip().lower()
    if not current.startswith("from:"):
        return False
    nearby = [
        str(line or "").strip().lower()
        for line in lines[index + 1:index + 6]
    ]
    return any(line.startswith(prefix) for line in nearby for prefix in ("sent:", "to:", "subject:"))
