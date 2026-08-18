import unittest

from unsubscribe_management import default_export_path


class UnsubscribeExportPathTest(unittest.TestCase):
    def test_default_export_path_uses_the_supplied_downloads_folder(self):
        self.assertEqual(
            default_export_path("/Users/example/Downloads"),
            "/Users/example/Downloads/unsubscribes.csv",
        )
