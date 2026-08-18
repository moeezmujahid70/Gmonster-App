import unittest

from unsubscribe_email import compose_alternatives


class UnsubscribeEmailTest(unittest.TestCase):
    def test_enabled_footer_is_added_to_both_alternatives(self):
        plain, html = compose_alternatives("Hello", "<p>Hello</p>",
                                           "https://server/unsubscribe?token=a&b=c", True)
        self.assertIn("Don't want to receive future emails from this sender?", plain)
        self.assertIn("https://server/unsubscribe?token=a&b=c", plain)
        self.assertIn("token=a&amp;b=c", html)
        self.assertIn(">Unsubscribe</a>.", html)

    def test_disabled_footer_leaves_bodies_unchanged(self):
        self.assertEqual(compose_alternatives("Hello", "<p>Hello</p>", "", False),
                         ("Hello", "<p>Hello</p>"))

