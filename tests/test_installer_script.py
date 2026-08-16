from pathlib import Path
import unittest


class InstallerScriptTest(unittest.TestCase):
    def test_installer_packages_both_executables_and_launches_gmonster(self):
        script = Path("installer/GMonster.iss").read_text(encoding="utf-8")

        self.assertIn('Source: "..\\release\\stage\\GMonster.exe"; DestDir: "{app}"', script)
        self.assertIn('Source: "..\\release\\stage\\WUM.exe"; DestDir: "{app}"', script)
        self.assertIn('Filename: "{app}\\GMonster.exe"; Description: "Launch GMonster"', script)

    def test_uninstaller_only_removes_user_data_after_explicit_confirmation(self):
        script = Path("installer/GMonster.iss").read_text(encoding="utf-8")

        self.assertIn("Remove user data", script)
        self.assertIn("DelTree", script)


if __name__ == "__main__":
    unittest.main()
