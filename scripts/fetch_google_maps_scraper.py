"""Download the pinned Google Maps scraper binary that GMonster bundles on Windows.

The binary is the open-source gosom/google-maps-scraper release. It is not kept in
git (``data/`` is ignored), so the Windows build fetches it and verifies its SHA-256
before PyInstaller packages it. Run this before ``pyinstaller GMonster.spec``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

# v1.18.3 uses mxschmitt/playwright-go; older builds download from a retired CDN.
SCRAPER_VERSION = "v1.18.3"
SCRAPER_URL = (
    "https://github.com/gosom/google-maps-scraper/releases/download/"
    f"{SCRAPER_VERSION}/google_maps_scraper-{SCRAPER_VERSION.removeprefix('v')}-windows-amd64.exe"
)
SCRAPER_SHA256 = "ad1f9be95a895d8a27afd36ebcc73a53e28069a5628521d39f30bf8d7e63f077"
DEFAULT_DESTINATION = Path("data/tools/google_maps_scraper/windows/google_maps_scraper.exe")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(destination: Path, url: str = SCRAPER_URL, sha256: str = SCRAPER_SHA256) -> Path:
    """Ensure ``destination`` holds the verified binary, downloading it if needed."""
    destination = Path(destination)
    if destination.is_file() and _sha256(destination) == sha256:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=destination.parent, suffix=".download")
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        with urllib.request.urlopen(url, timeout=120) as response, temp_path.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        actual = _sha256(temp_path)
        if actual != sha256:
            raise RuntimeError(
                f"Checksum mismatch for {url}: expected {sha256}, got {actual}"
            )
        os.replace(temp_path, destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return destination


def main() -> int:
    destination = fetch(DEFAULT_DESTINATION)
    print(f"Google Maps scraper {SCRAPER_VERSION} ready at {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
