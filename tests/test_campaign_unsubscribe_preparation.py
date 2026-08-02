import unittest
from unittest.mock import patch

from unsubscribe_client import PreparationError


class CampaignPreparationTest(unittest.TestCase):
    def test_assignments_include_sender_and_stable_ref(self):
        from smtp import build_sender_assignments
        import pandas as pd
        group = pd.DataFrame([{"EMAIL": "a@example.com"}, {"EMAIL": "b@example.com"}])
        targets = pd.DataFrame([{"EMAIL": f"lead{i}@example.com"} for i in range(3)])
        assignments = build_sender_assignments(group, targets, {0: 2, 1: 1})
        self.assertEqual([row["sender_email"] for row in assignments],
                         ["a@example.com", "a@example.com", "b@example.com"])
        self.assertEqual([row["ref"] for row in assignments], ["0", "1", "2"])

    @patch("smtp.prepare_batches", side_effect=PreparationError("offline"))
    def test_preparation_failure_returns_no_worker_payloads(self, prepare):
        from smtp import prepare_sender_assignments
        with self.assertRaises(PreparationError):
            prepare_sender_assignments([{"ref": "0", "email": "lead@example.com", "sender_email": "sales@example.com"}],
                                       "campaign", "Subject")
