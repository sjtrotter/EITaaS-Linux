import errno
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from eitaas import profiles
from eitaas.api import Application, ConnectionRequest
from eitaas.cli import main
from eitaas.profile import ProfileError

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic.rdpw"
LAUNCHER = "/usr/bin/eitaas-remmina"


class ProfileStoreTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(self._cleanup)
        self.downloads = self.home / "Downloads"
        self.downloads.mkdir()
        environment = patch.dict(
            os.environ,
            {
                "XDG_DATA_HOME": str(self.home / "share"),
                "XDG_CONFIG_HOME": str(self.home / "config"),
            },
        )
        environment.start()
        self.addCleanup(environment.stop)

    def _cleanup(self):
        for root, directories, files in os.walk(self.home, topdown=False):
            for name in files:
                Path(root, name).unlink()
            for name in directories:
                Path(root, name).rmdir()
        self.home.rmdir()

    def download(self, name="Desktop.rdpw", mode=0o644) -> Path:
        path = self.downloads / name
        path.write_bytes(FIXTURE.read_bytes())
        path.chmod(mode)
        return path

    def test_import_moves_restricts_and_sets_default(self):
        source = self.download()
        stored = profiles.import_profile(source)
        self.assertFalse(source.exists())
        self.assertEqual(stored.name, "Desktop.rdpw")
        self.assertEqual(stored.path, profiles.store_dir() / "Desktop.rdpw")
        self.assertEqual(stat.S_IMODE(stored.path.lstat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(profiles.store_dir().lstat().st_mode), 0o700)
        self.assertTrue(stored.default)
        self.assertEqual(profiles.default_profile().name, "Desktop.rdpw")
        config = profiles.config_path().read_text(encoding="utf-8")
        self.assertIn("default = Desktop.rdpw", config)
        self.assertNotIn("azure.us", config)
        self.assertEqual(stat.S_IMODE(profiles.config_path().lstat().st_mode), 0o600)

    def test_import_falls_back_to_copy_across_filesystems(self):
        source = self.download()

        def cross_device(src, dst, *args, **kwargs):
            raise OSError(errno.EXDEV, "Invalid cross-device link")

        with patch("eitaas.profiles.os.link", side_effect=cross_device) as link, \
                patch("eitaas.profiles._verify_stored", wraps=profiles._verify_stored) as verify:
            stored = profiles.import_profile(source)
        link.assert_called_once()
        verify.assert_called_once()
        self.assertFalse(source.exists())
        self.assertEqual(stored.path, profiles.store_dir() / "Desktop.rdpw")
        self.assertEqual(stored.path.read_bytes(), FIXTURE.read_bytes())
        self.assertEqual(stat.S_IMODE(stored.path.lstat().st_mode), 0o600)
        self.assertTrue(stat.S_ISREG(stored.path.lstat().st_mode))

    def test_duplicate_basenames_get_numeric_suffix(self):
        first = profiles.import_profile(self.download())
        second = profiles.import_profile(self.download())
        self.assertEqual([first.name, second.name], ["Desktop.rdpw", "Desktop-2.rdpw"])
        self.assertEqual(profiles.default_profile().name, "Desktop-2.rdpw")

    def test_import_refuses_symlinks_and_other_extensions(self):
        target = self.download()
        link = self.downloads / "link.rdpw"
        link.symlink_to(target)
        with self.assertRaises(ProfileError):
            profiles.import_profile(link)
        self.assertTrue(target.exists())
        with self.assertRaises(ProfileError):
            profiles.import_profile(self.download("Desktop.rdp"))
        self.assertEqual(profiles.list_profiles(), [])

    def test_import_errors_do_not_contain_paths(self):
        with self.assertRaises(ProfileError) as raised:
            profiles.import_profile(self.downloads / "missing.rdpw")
        self.assertNotIn(str(self.downloads), str(raised.exception))

    def test_select_and_remove(self):
        profiles.import_profile(self.download("A.rdpw"))
        profiles.import_profile(self.download("B.rdpw"))
        self.assertEqual(profiles.set_default("A.rdpw").name, "A.rdpw")
        self.assertEqual(profiles.default_profile().name, "A.rdpw")
        profiles.remove_profile("A.rdpw")
        self.assertEqual([item.name for item in profiles.list_profiles()], ["B.rdpw"])
        self.assertEqual(profiles.default_profile().name, "B.rdpw")
        with self.assertRaises(ProfileError):
            profiles.remove_profile("../B.rdpw")
        with self.assertRaises(ProfileError):
            profiles.remove_profile("missing.rdpw")

    def test_api_summaries_expose_names_only(self):
        result = Application().import_profile(str(self.download()))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value.name, "Desktop.rdpw")
        self.assertEqual(result.value.cloud, "azure_government")
        self.assertEqual(result.value.mode, "0600")
        self.assertTrue(result.value.default)
        self.assertFalse(hasattr(result.value, "path"))
        listed = Application().list_profiles()
        self.assertEqual([item.name for item in listed.value], ["Desktop.rdpw"])

    def test_api_import_failure_is_redacted(self):
        result = Application().import_profile(str(self.downloads / "none.rdpw"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "profile_import_failed")
        self.assertNotIn(str(self.downloads), result.error.message)

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.remmina.find_launcher", return_value=LAUNCHER)
    def test_launch_without_profile_uses_default(self, find_launcher, popen):
        popen.return_value = Mock(poll=Mock(return_value=0), returncode=0)
        stored = profiles.import_profile(self.download())
        result = Application().launch(ConnectionRequest())
        self.assertTrue(result.ok, result.error)
        self.assertEqual(popen.call_args.args, ([LAUNCHER, str(stored.path)],))

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.remmina.find_launcher", return_value=LAUNCHER)
    def test_launch_without_any_profile_fails_closed(self, find_launcher, popen):
        result = Application().launch(ConnectionRequest())
        self.assertFalse(result.ok)
        self.assertIn("eitaas profile import", result.error.message)
        popen.assert_not_called()

    def test_cli_profile_commands(self):
        source = self.download()
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["profile", "import", str(source)]), 0)
            self.assertEqual(main(["profile", "list"]), 0)
            self.assertEqual(main(["profile", "select", "Desktop.rdpw"]), 0)
            self.assertEqual(main(["profile", "remove", "Desktop.rdpw"]), 0)
        self.assertIn("name: Desktop.rdpw", output.getvalue())
        self.assertNotIn(str(self.downloads), output.getvalue())
        self.assertEqual(profiles.list_profiles(), [])
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(["profile", "remove", "Desktop.rdpw"]), 2)

    def test_symlink_swap_between_check_and_link_is_rejected(self):
        source = self.download()
        victim = self.home / "victim.txt"
        victim.write_text("secret")
        victim.chmod(0o644)
        real_link = os.link

        def swap_then_link(src, dst, **kwargs):
            Path(src).unlink()
            Path(src).symlink_to(victim)
            return real_link(src, dst, **kwargs)

        with patch("eitaas.profiles.os.link", side_effect=swap_then_link):
            with self.assertRaises(ProfileError):
                profiles.import_profile(source)
        self.assertEqual(profiles.list_profiles(), [])
        self.assertEqual(stat.S_IMODE(victim.lstat().st_mode), 0o644, "victim mode untouched")
        self.assertFalse(any(profiles.store_dir().iterdir()))

    def test_copy_path_rechecks_size_and_removes_partial_target(self):
        source = self.download()

        def grow_then_exdev(src, dst, **kwargs):
            with open(src, "ab") as handle:
                handle.write(b"x" * (profiles.MAX_PROFILE_SIZE + 1))
            raise OSError(18, "Invalid cross-device link")

        with patch("eitaas.profiles.os.link", side_effect=grow_then_exdev):
            with self.assertRaises(ProfileError):
                profiles.import_profile(source)
        self.assertTrue(source.exists(), "source is kept on failure")
        self.assertFalse(any(profiles.store_dir().iterdir()))

    def test_fifo_source_is_rejected_without_blocking(self):
        fifo = self.downloads / "pipe.rdpw"
        os.mkfifo(fifo)
        with self.assertRaises(ProfileError):
            profiles.import_profile(fifo)

    def test_invalid_after_move_is_removed_and_not_defaulted(self):
        source = self.download()
        with patch("eitaas.profiles.validate_profile", side_effect=ProfileError("bad")):
            with self.assertRaises(ProfileError):
                profiles.import_profile(source)
        self.assertFalse(any(profiles.store_dir().iterdir()))
        self.assertIsNone(profiles.default_profile())

    def test_default_fallback_skips_profiles_that_no_longer_validate(self):
        profiles.import_profile(self.download("A.rdpw"))
        second = profiles.import_profile(self.download("B.rdpw"))
        second.path.chmod(0o644)
        profiles._write_default_name(None)
        listed = {item.name: item for item in profiles.list_profiles()}
        self.assertFalse(listed["B.rdpw"].valid)
        self.assertEqual(profiles.default_profile().name, "A.rdpw")
        with self.assertRaises(ProfileError):
            profiles.set_default("B.rdpw")


if __name__ == "__main__":
    unittest.main()
