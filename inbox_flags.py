"""Read message identity and state from IMAP FETCH metadata."""

import imaplib
import re


def downloaded_message_metadata(header: bytes, tail: bytes = b"") -> tuple[str, str]:
    """Handle flags returned either before or after the message body literal."""
    metadata = header + b" " + tail
    uid_match = re.search(rb"\bUID\s+(\d+)\b", metadata, re.IGNORECASE)
    if uid_match is None:
        raise ValueError("IMAP FETCH response is missing the message UID")
    flags = imaplib.ParseFlags(metadata)
    is_read = any(flag.lower() == b"\\seen" for flag in flags)
    return uid_match.group(1).decode("ascii"), "SEEN" if is_read else "UNSEEN"
