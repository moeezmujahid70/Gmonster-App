import unittest

import pandas as pd

from inbox_search import filter_inbox_emails, normalize_inbox_search_query


class InboxSearchTest(unittest.TestCase):
    def setUp(self):
        self.emails = pd.DataFrame(
            [
                {
                    "from_name": "Alice Sales",
                    "from_mail": "alice@example.com",
                    "to_mail": "lead@example.com",
                    "subject": "Pricing follow up",
                    "body": "Can we discuss pricing tomorrow?",
                },
                {
                    "from_name": "Bob Ops",
                    "from_mail": "bob@example.com",
                    "to_mail": "sales@example.com",
                    "subject": "Meeting notes",
                    "body": "Internal notes only.",
                },
                {
                    "from_name": "Carol",
                    "from_mail": "carol@example.com",
                    "to_mail": "buyer@example.com",
                    "subject": "Demo",
                    "body": "The buyer asked about onboarding.",
                },
            ]
        )

    def test_normalize_query_strips_and_lowercases(self):
        self.assertEqual(normalize_inbox_search_query("  PriCing  "), "pricing")

    def test_empty_query_returns_original_dataframe(self):
        result = filter_inbox_emails(self.emails, "   ")

        self.assertIs(result, self.emails)

    def test_search_matches_sender_subject_recipient_and_body(self):
        self.assertEqual(
            filter_inbox_emails(self.emails, "alice")["subject"].tolist(),
            ["Pricing follow up"],
        )
        self.assertEqual(
            filter_inbox_emails(self.emails, "sales@example.com")["subject"].tolist(),
            ["Meeting notes"],
        )
        self.assertEqual(
            filter_inbox_emails(self.emails, "pricing")["subject"].tolist(),
            ["Pricing follow up"],
        )
        self.assertEqual(
            filter_inbox_emails(self.emails, "onboarding")["subject"].tolist(),
            ["Demo"],
        )

    def test_missing_searchable_columns_do_not_fail(self):
        partial = pd.DataFrame([{"subject": "Only subject"}, {"date": "2026-07-19"}])

        self.assertEqual(
            filter_inbox_emails(partial, "only")["subject"].tolist(),
            ["Only subject"],
        )
        self.assertEqual(len(filter_inbox_emails(partial, "missing")), 0)

    def test_no_searchable_columns_returns_original_dataframe(self):
        no_search_columns = pd.DataFrame([{"date": "2026-07-19"}])

        result = filter_inbox_emails(no_search_columns, "anything")

        self.assertIs(result, no_search_columns)


if __name__ == "__main__":
    unittest.main()
