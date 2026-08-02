import unittest
from unittest.mock import Mock, patch

import var
from gmonster_api import authenticated_request, capture_access_token


class GmonsterApiTest(unittest.TestCase):
    def setUp(self):
        var.api_access_token = ""

    def test_capture_access_token_keeps_it_in_memory(self):
        response = Mock(headers={"X-Gmonster-Access-Token": "token-1"})
        self.assertTrue(capture_access_token(response))
        self.assertEqual(var.api_access_token, "token-1")

    @patch("gmonster_api.refresh_access_token", return_value=True)
    def test_authenticated_request_refreshes_once_after_401(self, refresh):
        first, second = Mock(status_code=401), Mock(status_code=200)
        session = Mock()
        session.request.side_effect = [first, second]
        var.api_access_token = "old"
        response = authenticated_request("GET", "api/unsubscribe/setting", session=session)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.request.call_count, 2)
        refresh.assert_called_once()

