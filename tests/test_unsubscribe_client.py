import unittest
from unittest.mock import Mock, patch

from unsubscribe_client import PreparationError, prepare_batches


class UnsubscribeClientTest(unittest.TestCase):
    @patch("unsubscribe_client.authenticated_request")
    def test_prepares_1001_recipients_in_two_batches(self, request):
        def response_for_call(*args, **kwargs):
            recipients = kwargs["json"]["recipients"]
            return Mock(status_code=200, json=lambda: {
                "insert_unsubscribe_link": True,
                "results": [{"ref": row["ref"], "email": row["email"],
                             "status": "allowed", "unsubscribe_url": "https://server/u/" + row["ref"]}
                            for row in recipients],
            })
        request.side_effect = response_for_call
        assignments = [{"ref": str(i), "email": f"lead{i}@example.com", "sender_email": "sales@example.com"}
                       for i in range(1001)]
        enabled, prepared = prepare_batches(assignments, "campaign", "Subject", "initial")
        self.assertTrue(enabled)
        self.assertEqual(len(prepared), 1001)
        self.assertEqual(request.call_count, 2)

    @patch("unsubscribe_client.authenticated_request")
    def test_incomplete_response_aborts_preparation(self, request):
        request.return_value = Mock(status_code=200, json=lambda: {
            "insert_unsubscribe_link": True, "results": []})
        with self.assertRaises(PreparationError):
            prepare_batches([{"ref": "0", "email": "lead@example.com", "sender_email": "sales@example.com"}],
                            "campaign", "Subject", "initial")

    @patch("unsubscribe_client.authenticated_request")
    def test_setting_change_between_batches_aborts_preparation(self, request):
        def result(ref, enabled):
            row = {"ref": str(ref), "email": f"lead{ref}@example.com", "status": "allowed"}
            if enabled:
                row["unsubscribe_url"] = f"https://server/u/{ref}"
            return row
        request.side_effect = [
            Mock(status_code=200, json=lambda: {"insert_unsubscribe_link": True,
                                                  "results": [result(i, True) for i in range(1000)]}),
            Mock(status_code=200, json=lambda: {"insert_unsubscribe_link": False,
                                                  "results": [result(1000, False)]}),
        ]
        assignments = [{"ref": str(i), "email": f"lead{i}@example.com", "sender_email": "sales@example.com"}
                       for i in range(1001)]
        with self.assertRaises(PreparationError):
            prepare_batches(assignments, "campaign", "Subject", "initial")

