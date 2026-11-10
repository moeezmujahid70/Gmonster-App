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


from unittest.mock import Mock, patch

import requests

import var
from ai_generation import AIRequestError, AIResult, request_server_ai

SPINTAX = "{Hi|Hello} [1],\n\nI saw {your|the} work at [3].\n\n<b>Best</b> | {Regards|Thanks}"


def _response(status_code=200, payload=None, text="", json_error=False):
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    response.text = text
    if json_error:
        response.json.side_effect = ValueError("No JSON object could be decoded")
    else:
        response.json.return_value = payload
    return response


class ServerAIRequestTest(unittest.TestCase):
    def setUp(self):
        var.api = "https://api.example.test/"
        var.login_email = "user@example.test"
        var.login_password = "secret"
        var.login_machine_uuid = "machine-1"
        var.login_processor_id = "cpu-1"

    def _request(self, response=None, side_effect=None, prompt="Write an email"):
        with patch("ai_generation.requests.post") as post:
            post.return_value = response
            post.side_effect = side_effect
            try:
                result = request_server_ai(prompt)
                error = None
            except AIRequestError as caught:
                result, error = None, caught
        return result, error, post

    def test_success_returns_the_answer_and_optional_metadata(self):
        result, error, _ = self._request(_response(payload={
            "status": "ok",
            "answer": "Generated email body",
            "source": "server_fallback",
            "provider": "deepseek",
            "model": "deepseek-flash",
        }))

        self.assertIsNone(error)
        self.assertEqual(result, AIResult(
            answer="Generated email body",
            status="ok",
            source="server_fallback",
            provider="deepseek",
            model="deepseek-flash",
        ))

    def test_success_tolerates_missing_optional_fields_and_unknown_keys(self):
        result, error, _ = self._request(_response(payload={
            "answer": "Body", "something_new": {"nested": True},
        }))

        self.assertIsNone(error)
        self.assertEqual(result.answer, "Body")
        self.assertIsNone(result.provider)
        self.assertIsNone(result.model)
        self.assertIsNone(result.source)

    def test_request_keeps_the_existing_body_authentication_and_endpoint(self):
        _, _, post = self._request(_response(payload={"status": "ok", "answer": "x"}))

        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "https://api.example.test/verify/ai_response")
        self.assertEqual(post.call_args.kwargs["json"], {
            "email": "user@example.test",
            "password": "secret",
            "machine_uuid": "machine-1",
            "processor_id": "cpu-1",
            "prompt": "Write an email",
        })

    def test_read_timeout_is_45_seconds(self):
        _, _, post = self._request(_response(payload={"status": "ok", "answer": "x"}))

        self.assertEqual(post.call_args.kwargs["timeout"], (var.API_CONNECT_TIMEOUT, 45))

    def test_answer_text_is_returned_exactly(self):
        result, _, _ = self._request(_response(payload={"status": "ok", "answer": SPINTAX}))

        self.assertEqual(result.answer, SPINTAX)

    def test_empty_answer_is_reported_instead_of_blanking_the_editor(self):
        for payload in ({"status": "ok", "answer": ""}, {"status": "ok"}, {"answer": "   "}):
            with self.subTest(payload=payload):
                result, error, _ = self._request(_response(payload=payload))

                self.assertIsNone(result)
                self.assertIn("empty", error.message.lower())

    def test_http_200_with_an_error_payload_is_a_failure(self):
        result, error, _ = self._request(_response(payload={
            "status": "error", "message": "Out of credits", "retryable": False,
        }))

        self.assertIsNone(result)
        self.assertEqual(error.message, "Out of credits")
        self.assertFalse(error.retryable)

    def test_error_shows_the_server_message_and_retryable_flag(self):
        result, error, _ = self._request(_response(503, {
            "error": "ai_connection_error",
            "error_code": "ai_connection_error",
            "retryable": True,
            "message": "The AI service is busy. Please retry.",
        }))

        self.assertIsNone(result)
        self.assertEqual(error.message, "The AI service is busy. Please retry.")
        self.assertTrue(error.retryable)
        self.assertEqual(error.error_code, "ai_connection_error")

    def test_error_falls_back_to_the_error_field_when_message_is_missing(self):
        _, error, _ = self._request(_response(400, {"error": "Prompt is too long"}))

        self.assertEqual(error.message, "Prompt is too long")

    def test_error_without_message_or_error_uses_a_friendly_default(self):
        _, error, _ = self._request(_response(500, {"error_code": "ai_upstream_error"}))

        self.assertTrue(error.message)
        self.assertNotIn("ai_upstream_error", error.message)

    def test_error_is_not_retryable_unless_the_server_says_so(self):
        for payload in ({"message": "No"}, {"message": "No", "retryable": False},
                        {"message": "No", "retryable": "true"}):
            with self.subTest(payload=payload):
                _, error, _ = self._request(_response(500, payload))

                self.assertFalse(error.retryable)

    def test_non_json_gateway_error_is_handled_without_leaking_html(self):
        html = "<html><body><h1>502 Bad Gateway</h1></body></html>"
        result, error, post = self._request(
            _response(502, text=html, json_error=True)
        )

        self.assertIsNone(result)
        self.assertTrue(error.message)
        self.assertNotIn("<", error.message)
        self.assertFalse(error.retryable)
        self.assertEqual(post.call_count, 1)

    def test_non_json_success_response_is_handled(self):
        result, error, _ = self._request(_response(200, text="OK", json_error=True))

        self.assertIsNone(result)
        self.assertTrue(error.message)

    def test_json_that_is_not_an_object_is_handled(self):
        result, error, _ = self._request(_response(200, payload=["unexpected"]))

        self.assertIsNone(result)
        self.assertTrue(error.message)

    def test_timeout_is_reported_once_and_never_resent(self):
        result, error, post = self._request(side_effect=requests.exceptions.ReadTimeout())

        self.assertIsNone(result)
        self.assertEqual(post.call_count, 1)
        self.assertIn("still", error.message.lower())
        self.assertFalse(error.retryable)

    def test_connection_error_is_reported_once_and_never_resent(self):
        _, error, post = self._request(side_effect=requests.exceptions.ConnectionError())

        self.assertEqual(post.call_count, 1)
        self.assertIn("internet", error.message.lower())

    def test_retryable_server_errors_are_not_resent_automatically(self):
        _, error, post = self._request(_response(503, {"message": "Busy", "retryable": True}))

        self.assertTrue(error.retryable)
        self.assertEqual(post.call_count, 1)

    def test_unexpected_exceptions_become_friendly_errors(self):
        _, error, _ = self._request(side_effect=RuntimeError("boom"))

        self.assertNotIn("boom", error.message)
        self.assertTrue(error.message)
