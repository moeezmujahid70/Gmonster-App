import csv
import tempfile
import unittest

from unsubscribe_management import export_records, filter_records


class UnsubscribeManagementTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"email": "alice@example.com", "unsubscribed_at": "2026-07-19T01:00:00Z", "source": "link", "campaign_subject": "Pricing"},
            {"email": "bob@example.com", "unsubscribed_at": "2026-07-18T01:00:00Z", "source": "manual", "campaign_subject": None},
        ]

    def test_search_matches_email_source_and_subject(self):
        self.assertEqual([r["email"] for r in filter_records(self.rows, "pricing")], ["alice@example.com"])
        self.assertEqual([r["email"] for r in filter_records(self.rows, "manual")], ["bob@example.com"])

    def test_export_writes_only_supplied_filtered_rows(self):
        with tempfile.NamedTemporaryFile(suffix=".csv") as file:
            self.assertEqual(export_records(file.name, self.rows[:1]), 1)
            file.seek(0)
            rows = list(csv.DictReader(line.decode() for line in file.readlines()))
        self.assertEqual([row["email"] for row in rows], ["alice@example.com"])
