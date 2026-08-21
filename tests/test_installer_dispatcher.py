from pathlib import Path
import unittest


class InstallerDispatcherWorkflowTest(unittest.TestCase):
    def test_dispatcher_builds_a_selected_branch_without_publishing_a_release(self):
        workflow_path = Path(
            ".github/workflows/build-installer-from-branch.yml"
        )
        self.assertTrue(workflow_path.is_file(), "dispatcher workflow is missing")

        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("source_ref:", workflow)
        self.assertIn("release_version:", workflow)
        self.assertIn("wum_ref:", workflow)
        self.assertIn("console_build:", workflow)
        self.assertIn(
            "default: 227101e8aedddf8dad2dcff51d8df4fd01d3f48b", workflow
        )
        self.assertIn("ref: ${{ inputs.source_ref }}", workflow)
        self.assertIn("GMonster-${{ inputs.release_version }}-Setup", workflow)
        self.assertIn("GMONSTER_SMOKE_TEST_LOG", workflow)
        self.assertIn("GMONSTER_CONSOLE_BUILD", workflow)
        self.assertIn("Get-Content $smokeTestLog", workflow)
        self.assertLess(
            workflow.index("& .\\release-input\\wum\\WUM.exe --smoke-test"),
            workflow.index("$gmonster = Start-Process"),
        )
        self.assertNotIn("softprops/action-gh-release", workflow)


if __name__ == "__main__":
    unittest.main()
