"""Safe, actionable explanations for delivery and integration failures."""

from dataclasses import dataclass
import smtplib
import socket


@dataclass(frozen=True)
class UserMessage:
    code: str
    title: str
    body: str


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
