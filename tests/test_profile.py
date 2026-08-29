import os
import tempfile
import unittest
from pathlib import Path

from eitaas.profile import ProfileError, inspect_profile, validate_profile


class ProfileTests(unittest.TestCase):
    def make_profile(self, content: str = "redirectsmartcards:i:1\n") -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".rdpw", delete=False)
        path = Path(handle.name)
        handle.write(content.encode())
        handle.close()
        path.chmod(0o600)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_rejects_broad_permissions(self):
        path = self.make_profile()
        path.chmod(0o644)
        with self.assertRaises(ProfileError):
            validate_profile(path)

    def test_rejects_symlink(self):
        path = self.make_profile()
        link = path.with_name(path.name + ".link.rdpw")
        link.symlink_to(path)
        self.addCleanup(link.unlink, missing_ok=True)
        with self.assertRaises(ProfileError):
            validate_profile(link)

    def test_redacts_sensitive_fields(self):
        path = self.make_profile("loadbalanceinfo:s:secret\nusername:s:user@example.test\nredirectsmartcards:i:1\n")
        fields = inspect_profile(path)["fields"]
        self.assertEqual(fields[0]["value"], "<redacted>")
        self.assertEqual(fields[1]["value"], "<redacted>")
        self.assertEqual(fields[2]["value"], "1")


if __name__ == "__main__":
    unittest.main()
