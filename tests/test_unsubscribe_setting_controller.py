import unittest
from unittest.mock import Mock

from unsubscribe_setting import UnsubscribeSettingController


class UnsubscribeSettingControllerTest(unittest.TestCase):
    def test_failed_save_restores_previous_value(self):
        checkbox = Mock()
        checkbox.blockSignals.return_value = False
        controller = UnsubscribeSettingController(checkbox, load=lambda: False,
                                                  save=Mock(side_effect=RuntimeError("offline")))
        controller.current_value = False
        with self.assertRaises(RuntimeError):
            controller.persist_value(True)
        controller.restore_current_value()
        checkbox.setChecked.assert_called_with(False)
