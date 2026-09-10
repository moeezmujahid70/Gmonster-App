import unittest

import utils
import var


class LoginCredentialsConfigTest(unittest.TestCase):
    def setUp(self):
        self.original_email = var.login_email
        self.original_password = var.login_password
        self.original_remember = getattr(var, "remember_login_credentials", None)

    def tearDown(self):
        var.login_email = self.original_email
        var.login_password = self.original_password
        if self.original_remember is None:
            delattr(var, "remember_login_credentials")
        else:
            var.remember_login_credentials = self.original_remember

    def test_remembering_credentials_persists_email_and_password(self):
        var.login_email = "person@example.com"
        var.login_password = "remembered-password"
        var.remember_login_credentials = True

        config = utils.get_config_json()["config"]

        self.assertTrue(config["remember_login_credentials"])
        self.assertEqual(config["login_email"], "person@example.com")
        self.assertEqual(config["login_password"], "remembered-password")

    def test_not_remembering_credentials_omits_saved_password(self):
        var.login_email = "person@example.com"
        var.login_password = "do-not-save"
        var.remember_login_credentials = False

        config = utils.get_config_json()["config"]

        self.assertFalse(config["remember_login_credentials"])
        self.assertNotIn("login_password", config)

