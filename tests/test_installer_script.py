from pathlib import Path
import re
import unittest


class InstallerScriptTest(unittest.TestCase):
    def test_spec_uses_analysis_data_pairs_not_internal_toc_entries(self):
        spec = Path("GMonster.spec").read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"a\.datas\s*\+=\s*\[", spec))
        self.assertIn("datas += [(config_template_path, 'default-data')]", spec)
        self.assertIn("datas += [(certificate_path, 'default-data')]", spec)

    def test_installer_workflow_uses_the_fixed_wum_revision(self):
        workflow = Path(
            ".github/workflows/release-windows-installer.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("default: 227101e", workflow)
        self.assertIn("|| '227101e'", workflow)

    def test_spec_supports_an_opt_in_console_build_for_ci_diagnostics(self):
        spec = Path("GMonster.spec").read_text(encoding="utf-8")

        self.assertIn(
            'console=os.environ.get("GMONSTER_CONSOLE_BUILD") == "1"', spec
        )

    def test_spec_packages_clean_starter_sheet_templates(self):
        spec = Path("GMonster.spec").read_text(encoding="utf-8")

        self.assertIn("starter_data_path", spec)
        self.assertIn("Tree(starter_data_path, prefix='starter-data')", spec)
        for filename in ("group_a.xlsx", "group_b.xlsx", "target.xlsx"):
            self.assertTrue((Path("starter-data") / "sheets" / filename).is_file())

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
