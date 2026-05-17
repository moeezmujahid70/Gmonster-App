import os
import tempfile
import unittest

import pandas as pd

from statistics_report import (
    DateRange,
    StatisticsCalculator,
    StatisticsSummary,
    export_statistics_pdf,
)


class StatisticsCalculatorTest(unittest.TestCase):
    def _write_csv(self, directory, filename, content):
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)
        return path

    def test_counts_reports_replies_and_potential_earnings(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = self._write_csv(
                directory,
                "report.csv",
                "\n".join(
                    [
                        "TARGET,FROMEMAIL,STATUS,CAMPAIGN,DATE",
                        "lead1@example.com,sender@example.com,sent,camp-1,2026-05-01",
                        "TARGET,FROMEMAIL,STATUS,CAMPAIGN,DATE",
                        "lead2@example.com,sender@example.com,error,camp-1,2026-05-02",
                        "lead3@example.com,sender@example.com,sent,camp-1,2026-05-03",
                    ]
                ),
            )
            followup_path = self._write_csv(
                directory,
                "followup_report.csv",
                "\n".join(
                    [
                        "TARGET,FROMEMAIL,STATUS,CAMPAIGN,DATE",
                        "lead1@example.com,sender@example.com,sent,camp-1,2026-05-04",
                        "lead2@example.com,sender@example.com,failed,camp-1,2026-05-04",
                    ]
                ),
            )
            inbox = pd.DataFrame(
                [
                    {
                        "body": "Thanks, I am interested in learning more.",
                        "to_mail": "sender@example.com",
                        "date": "2026-05-05",
                        "is_sent": False,
                    },
                    {
                        "body": "No thanks, not interested.",
                        "to_mail": "sender@example.com",
                        "date": "2026-05-05",
                        "is_sent": False,
                    },
                    {
                        "body": "A sent mailbox item should not count as a reply.",
                        "to_mail": "lead@example.com",
                        "date": "2026-05-05",
                        "is_sent": True,
                    },
                ]
            )

            summary = StatisticsCalculator(
                report_path=report_path,
                followup_report_path=followup_path,
                negative_words=["no", "not interested", "stop"],
            ).calculate(
                inbox_tables=[inbox],
                date_range=DateRange.from_dates("2026-05-01", "2026-05-31"),
                product_price=1500,
            )

            self.assertEqual(summary.sent_emails, 2)
            self.assertEqual(summary.second_emails, 1)
            self.assertEqual(summary.positive_replies, 1)
            self.assertEqual(summary.negative_replies, 1)
            self.assertEqual(summary.potential_earnings, 1500)
            self.assertEqual(summary.daily_sent["2026-05-01"], 1)
            self.assertEqual(summary.daily_sent["2026-05-03"], 1)
            self.assertEqual(summary.daily_positive_replies["2026-05-05"], 1)

    def test_missing_sources_and_bad_price_return_zero_summary(self):
        summary = StatisticsCalculator(
            report_path="/missing/report.csv",
            followup_report_path="/missing/followup_report.csv",
            negative_words=["no"],
        ).calculate(inbox_tables=[pd.DataFrame()], product_price="not-a-number")

        self.assertEqual(summary.sent_emails, 0)
        self.assertEqual(summary.second_emails, 0)
        self.assertEqual(summary.positive_replies, 0)
        self.assertEqual(summary.negative_replies, 0)
        self.assertEqual(summary.potential_earnings, 0)

    def test_date_range_filters_all_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = self._write_csv(
                directory,
                "report.csv",
                "\n".join(
                    [
                        "TARGET,FROMEMAIL,STATUS,CAMPAIGN,DATE",
                        "old@example.com,sender@example.com,sent,camp-1,2026-04-30",
                        "new@example.com,sender@example.com,sent,camp-1,2026-05-02",
                    ]
                ),
            )
            followup_path = self._write_csv(
                directory,
                "followup_report.csv",
                "\n".join(
                    [
                        "TARGET,FROMEMAIL,STATUS,CAMPAIGN,DATE",
                        "old@example.com,sender@example.com,sent,camp-1,2026-04-30",
                        "new@example.com,sender@example.com,sent,camp-1,2026-05-02",
                    ]
                ),
            )
            inbox = pd.DataFrame(
                [
                    {
                        "body": "Interested before the date range.",
                        "to_mail": "sender@example.com",
                        "date": "2026-04-30",
                        "is_sent": False,
                    },
                    {
                        "body": "Interested inside the date range.",
                        "to_mail": "sender@example.com",
                        "date": "2026-05-02",
                        "is_sent": False,
                    },
                ]
            )

            summary = StatisticsCalculator(
                report_path=report_path,
                followup_report_path=followup_path,
            ).calculate(
                inbox_tables=[inbox],
                date_range=DateRange.from_dates("2026-05-01", "2026-05-31"),
                product_price=100,
            )

            self.assertEqual(summary.sent_emails, 1)
            self.assertEqual(summary.second_emails, 1)
            self.assertEqual(summary.positive_replies, 1)
            self.assertEqual(summary.potential_earnings, 100)

    def test_negative_sentiment_reply_counts_as_negative(self):
        inbox = pd.DataFrame(
            [
                {
                    "body": "This is terrible and disappointing.",
                    "to_mail": "sender@example.com",
                    "date": "2026-05-05",
                    "is_sent": False,
                },
            ]
        )

        summary = StatisticsCalculator(
            report_path="/missing/report.csv",
            followup_report_path="/missing/followup_report.csv",
            negative_words=["stop"],
        ).calculate(
            inbox_tables=[inbox],
            date_range=DateRange.from_dates("2026-05-01", "2026-05-31"),
        )

        self.assertEqual(summary.positive_replies, 0)
        self.assertEqual(summary.negative_replies, 1)

    def test_export_statistics_pdf_writes_pdf_without_pyqt(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = os.path.join(directory, "stats.pdf")
            export_statistics_pdf(
                output_path,
                StatisticsSummary(
                    sent_emails=22,
                    positive_replies=3,
                    negative_replies=1,
                    second_emails=5,
                    potential_earnings=4500,
                ),
                title="Outreach Performance",
                date_label="Last 30 days",
            )

            self.assertTrue(os.path.exists(output_path))
            with open(output_path, "rb") as file:
                self.assertEqual(file.read(4), b"%PDF")


if __name__ == "__main__":
    unittest.main()
