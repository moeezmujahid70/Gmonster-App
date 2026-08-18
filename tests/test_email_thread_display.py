import unittest


def body_to_thread_html(row_data):
    try:
        from email_thread_display import body_to_thread_html as render_body
    except ModuleNotFoundError as exc:
        raise AssertionError("email_thread_display.body_to_thread_html is missing") from exc
    return render_body(row_data)


def message_to_thread_html(row_data, show_metadata):
    try:
        from email_thread_display import message_to_thread_html as render_message
    except ImportError as exc:
        raise AssertionError("email_thread_display.message_to_thread_html is missing") from exc
    return render_message(row_data, show_metadata=show_metadata)


def header_date_text(row_data):
    try:
        from email_thread_display import header_date_text as format_date
    except ImportError as exc:
        raise AssertionError("email_thread_display.header_date_text is missing") from exc
    return format_date(row_data)


class EmailThreadDisplayTest(unittest.TestCase):
    def test_hungarian_gmail_quote_is_removed_from_inbound_reply(self):
        body = """Okay thanks man!

davidgreenberg329 aol <davidgreenberg329@aol.com> ezt írta (időpont: 2026.
jún. 16., K, 13:00):

> Here are the 10 most populous cities in Germany by city proper
> - Berlin
> - Hamburg
> For Pakistan, would you prefer:
"""

        rendered = body_to_thread_html({"body": body, "is_sent": False})

        self.assertIn("Okay thanks man!", rendered)
        self.assertNotIn("Berlin", rendered)
        self.assertNotIn("Hamburg", rendered)
        self.assertNotIn("For Pakistan", rendered)

    def test_english_gmail_quote_is_removed_from_inbound_reply(self):
        body = """Sounds good.

On Tue, Jun 16, 2026 at 1:00 PM David <david@example.com> wrote:
> Original message line
> More original content
"""

        rendered = body_to_thread_html({"body": body, "is_sent": False})

        self.assertIn("Sounds good.", rendered)
        self.assertNotIn("Original message line", rendered)
        self.assertNotIn("More original content", rendered)

    def test_html_quote_containers_are_removed_from_inbound_reply(self):
        body = """
<html><body>
<div>Okay thanks man!</div>
<div class="gmail_quote">
  <blockquote>Here are the 10 most populous cities in Germany</blockquote>
</div>
</body></html>
"""

        rendered = body_to_thread_html({"body": body, "is_sent": False})

        self.assertIn("Okay thanks man!", rendered)
        self.assertNotIn("Germany", rendered)
        self.assertNotIn("gmail_quote", rendered)
        self.assertNotIn("blockquote", rendered)

    def test_sent_messages_are_not_stripped(self):
        body = """Here are the 10 most populous cities in Germany:

- Berlin
- Hamburg

For Pakistan, would you prefer city-proper or metro populations?
"""

        rendered = body_to_thread_html({"body": body, "is_sent": True})

        self.assertIn("Berlin", rendered)
        self.assertIn("Hamburg", rendered)
        self.assertIn("For Pakistan", rendered)

    def test_selected_message_card_does_not_repeat_outer_metadata(self):
        rendered = message_to_thread_html(
            {
                "from": "András Czuczor en2contact@gmail.com",
                "to": "davidgreenberg329 aol davidgreenberg329@aol.com",
                "date": "2026-06-16 15:00:55",
                "subject": "Re: Small change, lasting boost for egy",
                "body": "Okay thanks man!",
                "is_sent": False,
            },
            show_metadata=False,
        )

        self.assertIn("Okay thanks man!", rendered)
        self.assertNotIn("Original email", rendered)
        self.assertNotIn("From:", rendered)
        self.assertNotIn("To:", rendered)
        self.assertNotIn("Date:", rendered)
        self.assertNotIn("Small change, lasting boost", rendered)

    def test_sent_older_message_separator_identifies_original_email_with_date(self):
        rendered = message_to_thread_html(
            {
                "from": "davidgreenberg329 aol davidgreenberg329@aol.com",
                "to": "en2contact@gmail.com",
                "date": "2026-06-16 15:00:12",
                "subject": "Small change, lasting boost for egy",
                "body": "Here are the 10 most populous cities in Germany:",
                "is_sent": True,
            },
            show_metadata=True,
        )

        self.assertIn("Original email", rendered)
        self.assertIn("2026-06-16 15:00:12", rendered)
        self.assertIn("Here are the 10 most populous cities", rendered)
        self.assertNotIn("From:", rendered)
        self.assertNotIn("To:", rendered)
        self.assertNotIn("Date:", rendered)
        self.assertNotIn("davidgreenberg329", rendered)
        self.assertNotIn("Small change, lasting boost", rendered)

    def test_inbound_older_message_separator_identifies_previous_reply_with_date(self):
        rendered = message_to_thread_html(
            {
                "from": "András Czuczor en2contact@gmail.com",
                "to": "davidgreenberg329 aol davidgreenberg329@aol.com",
                "date": "2026-06-16 15:02:01",
                "subject": "Re: Small change, lasting boost for egy",
                "body": "One more thing.",
                "is_sent": False,
            },
            show_metadata=True,
        )

        self.assertIn("Previous reply", rendered)
        self.assertIn("2026-06-16 15:02:01", rendered)
        self.assertIn("One more thing.", rendered)
        self.assertNotIn("Original email", rendered)
        self.assertNotIn("From:", rendered)
        self.assertNotIn("To:", rendered)

    def test_header_date_text_formats_selected_email_date(self):
        rendered = header_date_text({"date": "2026-06-16 15:00:55"})

        self.assertEqual(rendered, "2026-06-16 15:00:55")


if __name__ == "__main__":
    unittest.main()
