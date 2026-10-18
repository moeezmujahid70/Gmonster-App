import unittest

from ai_generation import email_reasoning_options


class EmailReasoningOptionsTest(unittest.TestCase):
    def test_gpt5_email_generation_uses_low_reasoning(self):
        for model in ('gpt-5-nano', 'gpt-5-mini', 'gpt-5', 'gpt-5.1'):
            with self.subTest(model=model):
                self.assertEqual(email_reasoning_options(model), {'reasoning_effort': 'low'})

    def test_models_without_reasoning_are_left_unchanged(self):
        for model in ('gpt-4.1-mini', 'gpt-4o', 'gpt-5-chat-latest', ''):
            with self.subTest(model=model):
                self.assertEqual(email_reasoning_options(model), {})
