import os
import sys
import types
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5 import QtCore, QtWidgets

from compat_ui import _open_log_folder, alert


class ErrorAlertLogsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_error_alert_opens_runtime_log_folder(self):
        observed = []

        def click_log_button():
            box = self.app.activeModalWidget()
            observed.extend(button.text() for button in box.buttons())
            for button in box.buttons():
                if button.text() == "Open log folder":
                    button.click()
                    break
            box.accept()

        runtime = types.SimpleNamespace(DATA_LOGS_DIR="/tmp/Gmonster installed/data/logs")
        with patch.dict(sys.modules, {"var": runtime}), patch(
            "PyQt5.QtGui.QDesktopServices.openUrl", return_value=True
        ) as open_url:
            QtCore.QTimer.singleShot(0, click_log_button)
            alert("Download failed", show_log_folder=True)

        self.assertIn("OK", observed)
        self.assertIn("Open log folder", observed)
        self.assertEqual(open_url.call_args.args[0].toLocalFile(), runtime.DATA_LOGS_DIR)

    def test_regular_alert_keeps_only_ok(self):
        observed = []

        def dismiss():
            box = self.app.activeModalWidget()
            observed.extend(button.text() for button in box.buttons())
            box.accept()

        QtCore.QTimer.singleShot(0, dismiss)
        alert("Saved")
        self.assertEqual(observed, ["OK"])

    def test_failed_folder_open_shows_the_location(self):
        runtime = types.SimpleNamespace(DATA_LOGS_DIR="/tmp/Gmonster installed/data/logs")
        with patch.dict(sys.modules, {"var": runtime}), patch(
            "PyQt5.QtGui.QDesktopServices.openUrl", return_value=False
        ), patch.object(QtWidgets.QMessageBox, "warning") as warning:
            _open_log_folder(None)

        self.assertIn(runtime.DATA_LOGS_DIR, warning.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
