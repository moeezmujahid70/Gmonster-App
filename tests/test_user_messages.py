import smtplib
import unittest

from user_messages import mailgenius_message, preparation_message, smtp_message


class UserMessagesTest(unittest.TestCase):
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
