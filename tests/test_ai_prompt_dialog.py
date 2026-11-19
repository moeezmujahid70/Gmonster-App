import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5 import QtCore, QtWidgets

import var
from ai_generation import AIRequestError
from ai_prompt_dialog import AIPromptDialog, show_answer_in_editor

SPINTAX = "{Hi|Hello} [1],\n\nI saw {your|the} work at [3].\n\n<b>Best</b> | {Regards|Thanks}"


class AIPromptDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        patcher = patch("ai_prompt_dialog.update_config_json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.release = threading.Event()
        self.calls = []
        self.dialogs = []
        self.submitted = []

    def tearDown(self):
        self.release.set()
        for dialog in self.dialogs:
            dialog.close()
        self.app.processEvents()

    def make_dialog(self, generate, prompt="Write a friendly intro"):
        dialog = AIPromptDialog(generate=generate)
        dialog.text_input.setPlainText(prompt)
        dialog.promptSubmitted.connect(self.submitted.append)
        self.dialogs.append(dialog)
        return dialog

    def wait_until(self, condition, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return
            time.sleep(0.005)
        self.fail("condition was not met in time")

    def assert_idle(self, dialog):
        self.assertTrue(dialog.send_button.isEnabled())
        self.assertTrue(dialog.loader.isHidden())
        self.assertFalse(dialog._slow_timer.isActive())

    def blocking(self, answer):
        def generate(prompt):
            self.calls.append(prompt)
            self.release.wait(5)
            return answer
        return generate

    def failing(self, error):
        def generate(prompt):
            self.calls.append(prompt)
            raise error
        return generate

    def test_slow_status_appears_after_15_seconds_by_default(self):
        self.assertEqual(AIPromptDialog.SLOW_STATUS_DELAY_MS, 15000)
        self.assertEqual(AIPromptDialog.SLOW_STATUS_TEXT, "Still generating your email…")

    def test_generate_is_disabled_and_a_loader_shows_while_the_request_runs(self):
        dialog = self.make_dialog(self.blocking("Hello"))

        dialog.send_button.click()

        self.assertFalse(dialog.send_button.isEnabled())
        self.assertFalse(dialog.loader.isHidden())
        self.assertFalse(dialog.status_label.isHidden())
        self.assertTrue(dialog.retry_button.isHidden())
        self.wait_until(lambda: self.calls)

    def test_success_emits_the_exact_answer_and_restores_the_controls(self):
        dialog = self.make_dialog(self.blocking(SPINTAX))
        dialog.send_button.click()
        self.release.set()

        self.wait_until(lambda: self.submitted)

        self.assertEqual(self.submitted, [SPINTAX])
        self.assert_idle(dialog)
        self.assertTrue(dialog.status_label.isHidden())
        self.assertEqual(self.calls, ["Write a friendly intro"])

    def test_delayed_response_switches_to_the_still_generating_message(self):
        dialog = self.make_dialog(self.blocking("Done"))
        dialog.SLOW_STATUS_DELAY_MS = 40
        dialog.send_button.click()
        first_message = dialog.status_label.text()

        self.wait_until(lambda: dialog.status_label.text() == "Still generating your email…")

        self.assertNotEqual(first_message, dialog.status_label.text())
        self.assertFalse(dialog.send_button.isEnabled())
        self.release.set()
        self.wait_until(lambda: self.submitted)
        self.assert_idle(dialog)

    def test_a_fast_response_never_shows_the_slow_message_later(self):
        dialog = self.make_dialog(lambda prompt: "Quick")
        dialog.SLOW_STATUS_DELAY_MS = 40
        dialog.send_button.click()
        self.wait_until(lambda: self.submitted)

        time.sleep(0.12)
        self.app.processEvents()

        self.assertTrue(dialog.status_label.isHidden())
        self.assertNotEqual(dialog.status_label.text(), "Still generating your email…")

    def test_retryable_error_shows_the_message_and_a_manual_retry(self):
        dialog = self.make_dialog(
            self.failing(AIRequestError("The AI service is busy. Please retry.", retryable=True))
        )
        dialog.send_button.click()

        self.wait_until(lambda: not dialog.retry_button.isHidden())

        self.assertEqual(dialog.status_label.text(), "The AI service is busy. Please retry.")
        self.assert_idle(dialog)
        self.assertEqual(self.submitted, [])
        self.assertEqual(len(self.calls), 1)

    def test_retry_resends_the_failed_prompt_and_clears_the_error(self):
        outcomes = [AIRequestError("Busy", retryable=True), "Second try worked"]

        def generate(prompt):
            self.calls.append(prompt)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        dialog = self.make_dialog(generate)
        dialog.send_button.click()
        self.wait_until(lambda: not dialog.retry_button.isHidden())
        dialog.text_input.setPlainText("edited after the failure")

        dialog.retry_button.click()
        self.wait_until(lambda: self.submitted)

        self.assertEqual(self.calls, ["Write a friendly intro", "Write a friendly intro"])
        self.assertEqual(self.submitted, ["Second try worked"])
        self.assertTrue(dialog.retry_button.isHidden())
        self.assertTrue(dialog.status_label.isHidden())
        self.assert_idle(dialog)

    def test_non_retryable_error_has_no_retry_button(self):
        dialog = self.make_dialog(self.failing(AIRequestError("Invalid account.", retryable=False)))
        dialog.send_button.click()

        self.wait_until(lambda: dialog.status_label.text() == "Invalid account.")

        self.assertTrue(dialog.retry_button.isHidden())
        self.assert_idle(dialog)

    def test_server_error_message_is_shown_as_plain_text_not_html(self):
        message = "Try <b>again</b> & {retry|later}"
        dialog = self.make_dialog(self.failing(AIRequestError(message)))
        dialog.send_button.click()

        self.wait_until(lambda: dialog.status_label.text() == message)

        self.assertEqual(dialog.status_label.textFormat(), QtCore.Qt.PlainText)

    def test_timeout_is_shown_once_and_never_resent_automatically(self):
        from ai_generation import ai_error_from_exception
        import requests

        error = ai_error_from_exception(requests.exceptions.ReadTimeout())
        dialog = self.make_dialog(self.failing(error))
        dialog.send_button.click()

        self.wait_until(lambda: dialog.status_label.text() == error.message)
        time.sleep(0.1)
        self.app.processEvents()

        self.assertEqual(len(self.calls), 1)
        self.assertTrue(dialog.retry_button.isHidden())
        self.assert_idle(dialog)

    def test_unexpected_exception_is_handled_and_controls_are_restored(self):
        dialog = self.make_dialog(self.failing(RuntimeError("internal detail")))
        dialog.send_button.click()

        self.wait_until(lambda: dialog.send_button.isEnabled() and not dialog.status_label.isHidden())

        self.assertNotIn("internal detail", dialog.status_label.text())
        self.assert_idle(dialog)

    def test_a_second_click_while_running_does_not_start_another_request(self):
        dialog = self.make_dialog(self.blocking("Once"))
        dialog.send_button.click()
        self.wait_until(lambda: self.calls)

        dialog.get_ai_response()

        self.release.set()
        self.wait_until(lambda: self.submitted)
        self.assertEqual(len(self.calls), 1)

    def test_empty_prompt_warns_without_sending_anything(self):
        dialog = self.make_dialog(self.blocking("x"), prompt="   ")

        with patch("ai_prompt_dialog.alert") as alert:
            dialog.send_button.click()

        alert.assert_called_once()
        self.assertEqual(self.calls, [])
        self.assert_idle(dialog)

    def test_closing_the_dialog_stops_the_slow_timer(self):
        dialog = self.make_dialog(self.blocking("late"))
        dialog.send_button.click()
        self.assertTrue(dialog._slow_timer.isActive())

        dialog.reject()

        self.assertFalse(dialog._slow_timer.isActive())

    def test_a_new_request_after_an_error_clears_the_previous_error(self):
        outcomes = [AIRequestError("First failed", retryable=True), "ok"]

        def generate(prompt):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        dialog = self.make_dialog(generate)
        dialog.send_button.click()
        self.wait_until(lambda: dialog.status_label.text() == "First failed")

        dialog.send_button.click()

        self.assertNotEqual(dialog.status_label.text(), "First failed")
        self.assertTrue(dialog.retry_button.isHidden())
        self.wait_until(lambda: self.submitted)


class AnswerDisplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_spintax_placeholders_and_paragraph_breaks_survive_display_and_copy(self):
        editor = QtWidgets.QTextBrowser()
        samples = (
            SPINTAX,
            "{A|B|{C|D}} [1] [2] [3]\n\n\nThree blank lines above",
            "<p>Not rich text</p>\n\n&amp; {x|y}",
            "Line one\nLine two\n\nParagraph two",
        )
        for text in samples:
            with self.subTest(text=text):
                show_answer_in_editor(editor, text)

                self.assertEqual(editor.toPlainText(), text)
                editor.selectAll()
                editor.copy()
                self.assertEqual(QtWidgets.QApplication.clipboard().text(), text)

    def test_html_looking_text_is_displayed_literally_not_parsed(self):
        editor = QtWidgets.QTextBrowser()
        show_answer_in_editor(editor, "<b>bold?</b>\n\nnext")

        self.assertEqual(editor.toPlainText(), "<b>bold?</b>\n\nnext")
        self.assertIn("&lt;b&gt;bold?&lt;/b&gt;", editor.toHtml())

    def test_setText_would_have_mangled_the_same_answer(self):
        # Documents why show_answer_in_editor uses setPlainText.
        editor = QtWidgets.QTextBrowser()
        editor.setText("<b>bold?</b>\n\nnext")

        self.assertNotEqual(editor.toPlainText(), "<b>bold?</b>\n\nnext")


if __name__ == "__main__":
    unittest.main()
