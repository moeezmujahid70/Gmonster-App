import unittest

from inbox_flags import downloaded_message_metadata


class InboxFlagsTest(unittest.TestCase):
    def test_read_email_stays_read_when_flags_precede_body(self):
        self.assertEqual(
            downloaded_message_metadata(b'7 (UID 123 FLAGS (\\Seen) RFC822 {500}', b')'),
            ('123', 'SEEN'),
        )

    def test_read_email_stays_read_when_flags_follow_body(self):
        self.assertEqual(
            downloaded_message_metadata(b'7 (UID 123 RFC822 {500}', b' FLAGS (\\Seen))'),
            ('123', 'SEEN'),
        )

    def test_uid_is_not_confused_with_other_metadata(self):
        self.assertEqual(
            downloaded_message_metadata(b'7 (FLAGS (\\Seen \\Answered) UID 456 RFC822 {500}', b')'),
            ('456', 'SEEN'),
        )

    def test_unread_email_stays_unread(self):
        self.assertEqual(
            downloaded_message_metadata(b'7 (UID 123 FLAGS (\\Recent \\Flagged) RFC822 {500}', b')'),
            ('123', 'UNSEEN'),
        )

    def test_seen_flag_is_case_insensitive_and_requires_exact_match(self):
        for flags, expected in ((b'\\seen', 'SEEN'), (b'NotSeen', 'UNSEEN'), (b'', 'UNSEEN')):
            with self.subTest(flags=flags):
                header = b'7 (UID 123 FLAGS (' + flags + b') RFC822 {500}'
                self.assertEqual(downloaded_message_metadata(header, b')')[1], expected)

    def test_missing_uid_is_rejected_instead_of_marking_wrong_email(self):
        with self.assertRaises(ValueError):
            downloaded_message_metadata(b'7 (FLAGS (\\Seen) RFC822 {500}', b')')
