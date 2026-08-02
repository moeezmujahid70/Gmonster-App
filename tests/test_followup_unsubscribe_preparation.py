import unittest
from unittest.mock import patch

from unsubscribe_client import PreparedRecipient


class FollowupPreparationTest(unittest.TestCase):
    @patch("smtp.prepare_batches")
    def test_suppressed_recipient_is_removed_before_followup_thread(self, prepare):
        from smtp import prepare_followup_groups
        prepare.return_value = (True, {
            "0:0": PreparedRecipient("0:0", "blocked@example.com", "suppressed"),
            "0:1": PreparedRecipient("0:1", "open@example.com", "allowed", "https://u/1"),
        })
        groups = [{"user": "sales@example.com", "target_info": [
            {"target_email": "blocked@example.com"}, {"target_email": "open@example.com"}]}]
        result = prepare_followup_groups(groups, "campaign", "Follow up")
        self.assertEqual([r["target_email"] for r in result[0]["target_info"]], ["open@example.com"])
        self.assertEqual(result[0]["target_info"][0]["unsubscribe_url"], "https://u/1")
