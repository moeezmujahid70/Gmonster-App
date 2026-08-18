import unittest

from campaign_progress import campaign_progress_state


class CampaignProgressTest(unittest.TestCase):
    def test_no_eligible_recipients_has_a_terminal_zero_progress_state(self):
        self.assertEqual(
            campaign_progress_state(sent=0, total=0, stopped=False),
            (0, "0/0", "No eligible recipients"),
        )
