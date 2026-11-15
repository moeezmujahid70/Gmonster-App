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

    def test_pins_the_release_with_the_retired_playwright_cdn_fix(self):
        self.assertIn("v1.18.3", fetcher.SCRAPER_URL)
        self.assertEqual(
            fetcher.SCRAPER_SHA256,
            "ad1f9be95a895d8a27afd36ebcc73a53e28069a5628521d39f30bf8d7e63f077",
        )


if __name__ == "__main__":
    unittest.main()
