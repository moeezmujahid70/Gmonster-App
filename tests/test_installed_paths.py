from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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
