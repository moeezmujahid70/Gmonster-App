import pathlib
import unittest
from unittest.mock import Mock, patch


class MailGeniusClientTest(unittest.TestCase):
    def test_config_export_keeps_only_the_mailgenius_enabled_setting(self):
        source = pathlib.Path("var.py").read_text(encoding="utf-8")

        self.assertIn('mailgenius = {\n    "enabled": False,\n}', source)
        self.assertNotIn('"rapidapi_key"', source)
        self.assertNotIn('"rapidapi_host"', source)

    def test_test_mail_sends_a_separate_visible_audit_copy(self):
        source = pathlib.Path("smtp.py").read_text(encoding="utf-8")

        self.assertIn('audit_message["To"] = self.audit_recipient', source)
        self.assertIn("MailGenius SMTP delivery was rejected", source)

    def test_send_dialog_uses_the_server_backed_mailgenius_client(self):
        source = pathlib.Path("send_dialog.py").read_text(encoding="utf-8")

        self.assertIn("MailGeniusClient().start_audit()", source)
        self.assertIn("MailGeniusClient().wait_for_result", source)
        self.assertNotIn("MailGeniusClient(var.mailgenius)", source)

    @patch("mailgenius._server_request")
    def test_start_audit_returns_server_owned_id_and_test_address(self, request):
        from mailgenius import MailGeniusClient

        request.return_value = Mock(
            status_code=201,
            json=lambda: {
                "audit_id": "0c6e4f05-2f9b-4ad3-9a30-6a8f6ef8a68f",
                "test_email": "test-audit-1@test.mailgenius.com",
            },
        )
        client = MailGeniusClient()

        audit = client.start_audit()

        self.assertEqual(audit.audit_id, "0c6e4f05-2f9b-4ad3-9a30-6a8f6ef8a68f")
        self.assertEqual(audit.test_email, "test-audit-1@test.mailgenius.com")
        request.assert_called_once_with("POST", "verify/mailgenius/audits")

    @patch("mailgenius._server_request")
    def test_wait_for_result_polls_the_server_owned_audit(self, request):
        from mailgenius import MailGeniusClient

        request.side_effect = [
            Mock(status_code=200, json=lambda: {"status": "pending"}),
            Mock(status_code=200, json=lambda: {"status": "complete", "spam_score": 8}),
        ]
        client = MailGeniusClient()

        result = client.wait_for_result(
            "0c6e4f05-2f9b-4ad3-9a30-6a8f6ef8a68f",
            attempts=2,
            interval_seconds=0,
            sleep=lambda _: None,
        )

        self.assertFalse(result.pending)
        self.assertEqual(result.data["spam_score"], 8)
        self.assertEqual(
            request.call_args_list[0].args,
            ("GET", "verify/mailgenius/audits/0c6e4f05-2f9b-4ad3-9a30-6a8f6ef8a68f"),
        )

    @patch("mailgenius._server_request")
    def test_default_wait_window_allows_two_minutes_thirty_seconds_for_analysis(
        self, request
    ):
        from mailgenius import MailGeniusClient, MailGeniusError

        pending = Mock(status_code=200, json=lambda: {"status": "pending"})
        complete = Mock(status_code=200, json=lambda: {"status": "complete"})
        request.side_effect = [pending] * 49 + [complete]
        client = MailGeniusClient()

        result = None
        try:
            result = client.wait_for_result(
                "0c6e4f05-2f9b-4ad3-9a30-6a8f6ef8a68f",
                interval_seconds=0,
                sleep=lambda _: None,
            )
        except MailGeniusError:
            pass

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "complete")
        self.assertEqual(request.call_count, 50)

    def test_detail_html_keeps_safe_links_and_removes_scripts(self):
        from mailgenius import sanitize_mailgenius_html

        rendered = sanitize_mailgenius_html(
            'Get <a href="https://example.com/help">help</a>'
            '<script>alert("unsafe")</script>.'
        )

        self.assertIn('<a href="https://example.com/help">help</a>', rendered)
        self.assertNotIn("<script", rendered)


if __name__ == "__main__":
    unittest.main()
