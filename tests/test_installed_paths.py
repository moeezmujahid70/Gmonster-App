from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import runtime_paths
from runtime_paths import run_smoke_test, update_staging_dir, wum_executable_path


class InstalledPathsTest(unittest.TestCase):
    def test_wum_executable_is_next_to_the_installed_application(self):
        self.assertEqual(
            wum_executable_path(Path("C:/Program Files/GMonster")),
            Path("C:/Program Files/GMonster/WUM.exe"),
        )

    def test_update_staging_uses_writable_runtime_data(self):
        self.assertEqual(
            update_staging_dir(Path("C:/Users/A/AppData/Local/GMonster/data")),
            Path("C:/Users/A/AppData/Local/GMonster/data/updates"),
        )

    def test_smoke_test_initializes_data_without_starting_a_gui(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory).resolve() / "GMonster" / "data"

            self.assertEqual(run_smoke_test(data_dir), 0)
            self.assertTrue((data_dir / "gmonster_config").is_dir())

    def test_smoke_test_writes_exception_details_when_initialization_fails(self):
        self.assertTrue(
            hasattr(runtime_paths, "run_smoke_test_with_diagnostics"),
            "diagnostic smoke-test runner is missing",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data_path = root / "data-file"
            data_path.write_text("not a directory", encoding="utf-8")
            diagnostic_path = root / "smoke-test-error.log"

            self.assertEqual(
                runtime_paths.run_smoke_test_with_diagnostics(
                    data_path, diagnostic_path
                ),
                1,
            )
            self.assertIn("NotADirectoryError", diagnostic_path.read_text(encoding="utf-8"))

    def test_var_smoke_test_exits_without_importing_gui_dependencies(self):
        repository_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(repository_root / "var.py"), "--smoke-test"],
                cwd=directory,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
