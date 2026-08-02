import pathlib
import unittest


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        return self.responses.pop(0)


class MailGeniusClientTest(unittest.TestCase):
    def test_config_export_preserves_mailgenius_settings(self):
        source = pathlib.Path("utils.py").read_text(encoding="utf-8")

        self.assertIn('"mailgenius": var.mailgenius,', source)

    def test_test_mail_sends_a_separate_visible_audit_copy(self):
        source = pathlib.Path("smtp.py").read_text(encoding="utf-8")

        self.assertIn('audit_message["To"] = self.audit_recipient', source)
        self.assertIn("MailGenius SMTP delivery was rejected", source)

    def test_start_audit_returns_slug_and_test_address(self):
        from mailgenius import MailGeniusClient

        session = FakeSession(
            [FakeResponse({"test_email": "test-audit-1@test.mailgenius.com"})]
        )
        client = MailGeniusClient(
            {"rapidapi_key": "key", "rapidapi_host": "host.test"},
            session=session,
        )

        audit = client.start_audit()

        self.assertEqual(audit.slug, "audit-1")
        self.assertEqual(audit.test_email, "test-audit-1@test.mailgenius.com")
        self.assertEqual(
            session.calls[0][0],
            "https://host.test/external/api/email-audit",
        )
        self.assertEqual(session.calls[0][1]["x-rapidapi-host"], "host.test")

    def test_wait_for_result_returns_first_completed_response(self):
        from mailgenius import MailGeniusClient

        session = FakeSession(
            [
                FakeResponse({"slug": "audit-1", "status": "pending"}),
                FakeResponse(
                    {"slug": "audit-1", "status": "complete", "spam_score": 8}
                ),
            ]
        )
        client = MailGeniusClient(
            {"rapidapi_key": "key", "rapidapi_host": "host.test"},
            session=session,
        )

        result = client.wait_for_result(
            "audit-1", attempts=2, interval_seconds=0, sleep=lambda _: None
        )

        self.assertFalse(result.pending)
        self.assertEqual(result.data["spam_score"], 8)


if __name__ == "__main__":
    unittest.main()
