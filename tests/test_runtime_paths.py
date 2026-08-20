from pathlib import Path
import tempfile
import unittest

from runtime_paths import (
    initialize_runtime_data,
    open_sheets_folder,
    resolve_runtime_paths,
)


class RuntimePathsTest(unittest.TestCase):
    def test_frozen_windows_uses_local_app_data_for_writable_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            paths = resolve_runtime_paths(
                frozen=True,
                platform_name="win32",
                executable=root / "Program Files" / "GMonster" / "GMonster.exe",
                resource_dir=root / "resources",
                working_dir=root / "ignored",
                local_app_data=root / "Users" / "A" / "AppData" / "Local",
            )

            self.assertEqual(paths.app_dir, root / "Program Files" / "GMonster")
            self.assertEqual(
                paths.data_dir,
                root / "Users" / "A" / "AppData" / "Local" / "GMonster" / "data",
            )

    def test_development_uses_repository_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            paths = resolve_runtime_paths(
                frozen=False,
                platform_name="darwin",
                executable=root / "ignored",
                resource_dir=root / "ignored",
                working_dir=root / "repo",
                local_app_data=root / "ignored",
            )

            self.assertEqual(paths.app_dir, root / "repo")
            self.assertEqual(paths.data_dir, root / "repo" / "data")

    def test_initialize_runtime_data_seeds_config_only_when_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            defaults = root / "defaults"
            defaults.mkdir()
            (defaults / "config.json").write_text('{"config": {}}', encoding="utf-8")
            destination = root / "runtime" / "data"

            initialize_runtime_data(destination, defaults, legacy_data_dir=None)
            config_path = destination / "gmonster_config" / "config.json"
            self.assertEqual(config_path.read_text(encoding="utf-8"), '{"config": {}}')

            config_path.write_text('{"config": {"user": true}}', encoding="utf-8")
            initialize_runtime_data(destination, defaults, legacy_data_dir=None)
            self.assertEqual(
                config_path.read_text(encoding="utf-8"),
                '{"config": {"user": true}}',
            )

    def test_initialize_runtime_data_uses_config_example_as_a_safe_template(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            defaults = root / "defaults"
            defaults.mkdir()
            (defaults / "config.example.json").write_text(
                '{"config": {"safe": true}}', encoding="utf-8"
            )
            destination = root / "runtime" / "data"

            initialize_runtime_data(destination, defaults, legacy_data_dir=None)

            self.assertEqual(
                (destination / "gmonster_config" / "config.json").read_text(
                    encoding="utf-8"
                ),
                '{"config": {"safe": true}}',
            )

    def test_initialize_runtime_data_seeds_starter_sheets_without_replacing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            starter_data = root / "starter-data"
            starter_sheets = starter_data / "sheets"
            starter_sheets.mkdir(parents=True)
            (starter_sheets / "target.xlsx").write_bytes(b"starter-target")
            (starter_sheets / "group_a.xlsx").write_bytes(b"starter-group-a")
            destination = root / "runtime" / "data"

            initialize_runtime_data(
                destination,
                root / "defaults",
                legacy_data_dir=None,
                starter_data_dir=starter_data,
            )

            target = destination / "sheets" / "target.xlsx"
            self.assertEqual(target.read_bytes(), b"starter-target")
            self.assertEqual(
                (destination / "sheets" / "group_a.xlsx").read_bytes(),
                b"starter-group-a",
            )

            target.write_bytes(b"customer-target")
            initialize_runtime_data(
                destination,
                root / "defaults",
                legacy_data_dir=None,
                starter_data_dir=starter_data,
            )
            self.assertEqual(target.read_bytes(), b"customer-target")

    def test_initialize_runtime_data_preserves_newer_files_during_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            legacy_data = root / "legacy" / "data"
            (legacy_data / "sheets").mkdir(parents=True)
            (legacy_data / "sheets" / "targets.xlsx").write_bytes(b"legacy")
            destination = root / "runtime" / "data"
            (destination / "sheets").mkdir(parents=True)
            (destination / "sheets" / "targets.xlsx").write_bytes(b"current")

            initialize_runtime_data(destination, root / "defaults", legacy_data)

            self.assertEqual(
                (destination / "sheets" / "targets.xlsx").read_bytes(), b"current"
            )

    def test_open_sheets_folder_creates_and_opens_the_runtime_sheets_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory).resolve() / "data"
            opened_paths = []

            sheets_dir = open_sheets_folder(data_dir, opened_paths.append)

            self.assertEqual(sheets_dir, data_dir / "sheets")
            self.assertTrue(sheets_dir.is_dir())
            self.assertEqual(opened_paths, [sheets_dir])


if __name__ == "__main__":
    unittest.main()
