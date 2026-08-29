import pathlib
import unittest
import xml.etree.ElementTree as ET


class DatabaseUiDefaultsTest(unittest.TestCase):
    def test_select_filters_start_collapsed_with_shared_button_typography(self):
        root = ET.parse("ui/gui.ui").getroot()
        select_toggle = next(
            widget
            for widget in root.iter("widget")
            if widget.get("name") == "pushButton_select_toggle"
        )

        self.assertEqual(
            select_toggle.findtext("property[@name='checked']/bool"), "false"
        )
        self.assertEqual(
            select_toggle.findtext("property[@name='text']/string"), "► Select"
        )

        date_picker = next(
            widget
            for widget in root.iter("widget")
            if widget.get("name") == "dateEdit_imap_since"
        )
        date_picker_style = date_picker.findtext(
            "property[@name='styleSheet']/string"
        )
        self.assertIn("QDateEdit::drop-down", date_picker_style)
        self.assertIn("background: transparent", date_picker_style)
        self.assertIn("border: none", date_picker_style)
        self.assertNotIn("QDateEdit::down-arrow", date_picker_style)

        source = pathlib.Path("main.py").read_text(encoding="utf-8")
        self.assertIn("QPushButton, QToolButton", source)
        self.assertIn("font-family: Arial; font-weight: 400;", source)
        self.assertIn("GUI.frame_checkboxes.setVisible(False)", source)


if __name__ == "__main__":
    unittest.main()
