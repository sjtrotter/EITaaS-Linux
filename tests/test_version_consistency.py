import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "scripts/check-version-consistency.py"


class VersionConsistencyTests(unittest.TestCase):
    def run_checker(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--project-root", str(PROJECT_ROOT), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_all_version_declarations_match(self):
        result = self.run_checker("--tag", "v0.2.0")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mismatched_release_tag_is_rejected(self):
        result = self.run_checker("--tag", "v0.2.1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release tag=0.2.1", result.stderr)


if __name__ == "__main__":
    unittest.main()
