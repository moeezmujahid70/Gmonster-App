import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path("scripts").resolve()))

import fetch_google_maps_scraper as fetcher


class FetchGoogleMapsScraperTest(unittest.TestCase):
    def _source(self, root, payload=b"scraper-binary"):
        source = root / "source.exe"
        source.write_bytes(payload)
        return source, hashlib.sha256(payload).hexdigest()

    def test_downloads_and_verifies_the_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, digest = self._source(root)
            destination = root / "out" / "windows" / "google_maps_scraper.exe"

            fetcher.fetch(destination, source.as_uri(), digest)

            self.assertEqual(destination.read_bytes(), b"scraper-binary")

    def test_rejects_a_download_with_the_wrong_checksum_and_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _ = self._source(root)
            destination = root / "out" / "google_maps_scraper.exe"

            with self.assertRaises(RuntimeError):
                fetcher.fetch(destination, source.as_uri(), "0" * 64)

            self.assertFalse(destination.exists())

    def test_skips_the_download_when_a_valid_binary_is_already_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, digest = self._source(root)
            destination = root / "google_maps_scraper.exe"
            destination.write_bytes(b"scraper-binary")

            fetcher.fetch(destination, (root / "missing.exe").as_uri(), digest)

            self.assertEqual(destination.read_bytes(), b"scraper-binary")

    def test_replaces_a_corrupt_existing_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, digest = self._source(root)
            destination = root / "google_maps_scraper.exe"
            destination.write_bytes(b"corrupt")

            fetcher.fetch(destination, source.as_uri(), digest)

            self.assertEqual(destination.read_bytes(), b"scraper-binary")

    def test_pins_the_release_that_matches_the_binary_gmonster_was_built_with(self):
        self.assertIn("v1.11.0", fetcher.SCRAPER_URL)
        self.assertEqual(
            fetcher.SCRAPER_SHA256,
            "41cf2df1cdd4d3ce0cef54d9f4d09f8c34257a97ec4d59eb7bc0140065592594",
        )


if __name__ == "__main__":
    unittest.main()
