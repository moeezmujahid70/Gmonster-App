import pathlib
import unittest


class SidebarToolsMenuTest(unittest.TestCase):
    def test_tools_menu_hides_secondary_entries_without_removing_their_actions(self):
        source = pathlib.Path("main.py").read_text(encoding="utf-8")

        self.assertIn("TOOL_NAVIGATION_ITEMS", source)
        self.assertIn("def setup_sidebar_tools_menu", source)
        self.assertIn("item.setHidden(True)", source)
        self.assertIn("QtCore.Qt.ScrollBarAlwaysOff", source)
        self.assertIn("def show_tools_menu", source)
        self.assertIn("self.navigate_to_item", source)
        self.assertIn("TOOL_MENU_ICON_NAMES", source)
        self.assertIn("action.setIcon", source)
        self.assertIn("menu.setMinimumWidth(210)", source)
        self.assertIn("QMenu::item:selected", source)


if __name__ == "__main__":
    unittest.main()
