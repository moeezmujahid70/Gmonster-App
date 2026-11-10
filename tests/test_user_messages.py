import smtplib
import unittest

from user_messages import (
    display_text,
    login_response_message,
    mailgenius_message,
    operation_message,
    preparation_message,
    smtp_message,
    summary_text,
)


class UserMessagesTest(unittest.TestCase):
    def test_login_authentication_error_explains_app_password_without_server_text(self):
        message = operation_message(
            "login", smtplib.SMTPAuthenticationError(535, b"invalid credentials")
        )

        self.assertEqual(message.code, "AUTH_INVALID")
        self.assertIn("app password", message.body.lower())
        self.assertNotIn("invalid credentials", display_text(message).lower())

    def test_timeout_explains_retry_without_leaking_exception_detail(self):
        message = operation_message(
            "imap_download", TimeoutError("proxy_password=do-not-show")
        )

        self.assertEqual(message.code, "CONNECTION_TIMEOUT")
        self.assertIn("retry", message.body.lower())
        self.assertNotIn("do-not-show", display_text(message))

    def test_summary_deduplicates_error_references(self):
        message = operation_message("campaign", TimeoutError())

        rendered = summary_text([message, message])

        self.assertEqual(rendered.count("CONNECTION_TIMEOUT"), 1)

    def test_login_rejection_is_translated_without_exposing_backend_copy(self):
        message = login_response_message("Invalid login password")

        self.assertEqual(message.code, "AUTH_INVALID")
        self.assertIn("password", message.body.lower())
        self.assertNotIn("invalid login password", display_text(message).lower())

    def test_smtp_authentication_explains_the_next_step(self):
        message = smtp_message(smtplib.SMTPAuthenticationError(535, b"invalid credentials"))
        self.assertEqual(message.code, "SMTP_AUTH")
        self.assertIn("password", message.body.lower())
        self.assertNotIn("invalid credentials", message.body)

    def test_preparation_setting_change_tells_user_to_retry(self):
        message = preparation_message(RuntimeError("Unsubscribe setting changed during preparation; please retry"))
        self.assertEqual(message.code, "UNSUB_SETTING_CHANGED")
        self.assertIn("retry", message.body.lower())

    def test_mailgenius_timeout_does_not_claim_the_test_email_failed(self):
        message = mailgenius_message(RuntimeError("MailGenius analysis timed out. Please try again."))
        self.assertEqual(message.code, "MAILGENIUS_TIMEOUT")
        self.assertIn("sent", message.body.lower())

    def test_mailgenius_server_configuration_message_never_requests_a_rapidapi_key(self):
        message = mailgenius_message(
            RuntimeError("MailGenius is not configured on the server.")
        )

        self.assertEqual(message.code, "MAILGENIUS_CONFIG")
        self.assertIn("server", message.body.lower())
        self.assertNotIn("rapidapi", message.body.lower())
