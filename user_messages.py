"""Safe, actionable explanations for delivery and integration failures."""

from dataclasses import dataclass
from collections.abc import Iterable
from typing import Optional
import imaplib
import smtplib
import socket

import requests


@dataclass(frozen=True)
class UserMessage:
    code: str
    title: str
    body: str


def display_text(message: UserMessage) -> str:
    """Render a safe, support-ready explanation for a UI label or alert."""
    return "{}\n{}\n\nError reference: {}".format(
        message.title, message.body, message.code
    )


def summary_text(messages: Iterable[UserMessage]) -> str:
    """Render each failure category once for a bulk-operation summary."""
    unique_messages = {}
    for message in messages:
        unique_messages[message.code] = message
    return "\n\n".join(display_text(message) for message in unique_messages.values())


def operation_message(
    operation: str, error: Optional[Exception] = None, *, rejected: bool = False
) -> UserMessage:
    """Translate a technical operation failure into safe user guidance."""
    if rejected or isinstance(error, smtplib.SMTPRecipientsRefused):
        return UserMessage(
            "RECIPIENT_REJECTED",
            "Recipient address was rejected",
            "The mail provider rejected the recipient address. Check the address and try again.",
        )

    if isinstance(error, smtplib.SMTPResponseException):
        if error.smtp_code in (535, 534):
            return UserMessage(
                "AUTH_INVALID",
                "Account could not sign in",
                "Check the email and password. Some providers require an app password.",
            )
        if error.smtp_code in (421, 450, 451, 452):
            return UserMessage(
                "PROVIDER_BLOCKED",
                "Mail provider paused this sender",
                "Check the mailbox for a provider notice, then retry later.",
            )

    if isinstance(error, imaplib.IMAP4.error):
        return UserMessage(
            "AUTH_INVALID",
            "Account could not sign in",
            "Check the email and password. Some providers require an app password.",
        )

    if isinstance(error, (TimeoutError, requests.exceptions.Timeout)):
        return UserMessage(
            "CONNECTION_TIMEOUT",
            "The service took too long to respond",
            "Wait briefly and retry.",
        )

    if isinstance(
        error,
        (
            socket.gaierror,
            ConnectionError,
            requests.exceptions.ConnectionError,
            smtplib.SMTPConnectError,
        ),
    ):
        return UserMessage(
            "CONNECTION_FAILED",
            "Could not reach the service",
            "Check your internet connection and proxy settings, then retry.",
        )

    status_code = getattr(getattr(error, "response", None), "status_code", None)
    if status_code in (401, 403):
        return UserMessage(
            "AUTH_INVALID",
            "Account could not sign in",
            "Check the email and password, then retry.",
        )
    if status_code in (408, 504):
        return UserMessage(
            "CONNECTION_TIMEOUT",
            "The service took too long to respond",
            "Wait briefly and retry.",
        )
    if status_code == 429 or (isinstance(status_code, int) and status_code >= 500):
        return UserMessage(
            "SERVICE_UNAVAILABLE",
            "Gmonster service is unavailable",
            "Retry shortly. If this continues, contact support with the error reference.",
        )

    if operation in {"login", "signup"} and isinstance(error, ValueError):
        return UserMessage(
            "INPUT_INVALID",
            "Check the information entered",
            "Enter a valid email address and password, then retry.",
        )

    return UserMessage(
        "OPERATION_FAILED",
        "Operation could not be completed",
        "Check the account and connection, then retry.",
    )


def login_response_message(response_text: str, endpoint: str = "login") -> UserMessage:
    """Translate an untrusted authentication response into safe UI copy."""
    detail = str(response_text or "").strip().lower()
    if any(token in detail for token in ("password", "credential", "invalid login", "not found")):
        return UserMessage(
            "AUTH_INVALID",
            "Account could not sign in",
            "Check the email and password, then try again.",
        )
    if endpoint == "register" and any(token in detail for token in ("exists", "already", "registered")):
        return UserMessage(
            "ACCOUNT_EXISTS",
            "Account already exists",
            "Try signing in instead, or use a different email address.",
        )
    return UserMessage(
        "SERVICE_UNAVAILABLE",
        "Gmonster service is unavailable",
        "Retry shortly. If this continues, contact support with the error reference.",
    )


def smtp_message(error=None, rejected=False) -> UserMessage:
    if rejected or isinstance(error, smtplib.SMTPRecipientsRefused):
        return UserMessage(
            "SMTP_RECIPIENT_REJECTED",
            "Recipient address was rejected",
            "The mail provider rejected the recipient address. Check the address and try again.",
        )
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return UserMessage(
            "SMTP_AUTH",
            "Sender account could not sign in",
            "Check the sender account password or app password, then try again.",
        )
    if isinstance(error, (smtplib.SMTPConnectError, socket.gaierror, TimeoutError)):
        return UserMessage(
            "SMTP_CONNECTION",
            "Could not reach the mail provider",
            "Check your internet connection and proxy settings, then try again.",
        )
    return UserMessage(
        "SMTP_SEND_FAILED",
        "Email could not be sent",
        "Check the sender account and connection, then try again. If it continues, contact support with the error reference.",
    )


def preparation_message(error) -> UserMessage:
    detail = str(error).lower()
    if "setting changed" in detail:
        return UserMessage(
            "UNSUB_SETTING_CHANGED",
            "Unsubscribe setting changed",
            "The unsubscribe setting changed while recipients were being checked. No emails were sent; please retry the campaign.",
        )
    if "no eligible" in detail:
        return UserMessage(
            "UNSUB_NO_ELIGIBLE",
            "No eligible recipients",
            "All remaining recipients are unsubscribed or invalid, so no emails were sent.",
        )
    return UserMessage(
        "UNSUB_PREPARATION_FAILED",
        "Could not verify unsubscribe status",
        "No emails were sent. Check your connection and retry the campaign.",
    )


def mailgenius_message(error) -> UserMessage:
    detail = str(error).lower()
    if "not configured" in detail:
        return UserMessage(
            "MAILGENIUS_CONFIG",
            "MailGenius is not configured",
            "MailGenius is not configured on the server. Contact support if this continues.",
        )
    if "timed out" in detail:
        return UserMessage(
            "MAILGENIUS_TIMEOUT",
            "MailGenius is still processing",
            "The test email was sent, but MailGenius did not finish in time. Please try again shortly.",
        )
    if "connection" in detail:
        return UserMessage(
            "MAILGENIUS_CONNECTION",
            "Could not reach MailGenius",
            "Check your connection and GMonster server configuration, then try again.",
        )
    return UserMessage(
        "MAILGENIUS_FAILED",
        "MailGenius could not complete the check",
        "The test email may have been sent, but deliverability results are unavailable. Please try again.",
    )


def followup_message(error) -> UserMessage:
    if "unsubscribe" in str(error).lower():
        return UserMessage(
            "FOLLOWUP_UNSUB_VERIFY",
            "Follow-up was not sent",
            "Recipient unsubscribe status could not be verified. No follow-up emails were sent; please retry later.",
        )
    return UserMessage(
        "FOLLOWUP_FAILED",
        "Follow-up could not be completed",
        "No further follow-up emails were sent. Check the sender account and connection, then retry later.",
    )
