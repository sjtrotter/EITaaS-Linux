import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from eitaas.api import Application, ConnectionRequest, ConnectionResult, Result
from eitaas.cli import main

LAUNCHER = "/usr/bin/eitaas-remmina"


class LaunchTests(unittest.TestCase):
    def profile(self) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".rdpw", delete=False)
        path = Path(handle.name)
        handle.write(
            b"redirectsmartcards:i:1\n"
            b"full address:s:synthetic.wvd.azure.us\n"
        )
        handle.close()
        path.chmod(0o600)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.remmina.find_launcher", return_value=LAUNCHER)
    def test_launcher_receives_fixed_argv_and_no_stdio(self, find_launcher, popen):
        popen.return_value = Mock(poll=Mock(return_value=0), returncode=0)
        profile = self.profile()
        result = Application().launch(ConnectionRequest(str(profile)))
        self.assertTrue(result.ok)
        self.assertEqual(result.value, ConnectionResult(0))
        self.assertEqual(popen.call_args.args, ([LAUNCHER, str(profile)],))
        self.assertEqual(
            popen.call_args.kwargs,
            {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            },
        )

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.remmina.find_launcher", return_value=None)
    def test_missing_launcher_fails_before_spawning(self, find_launcher, popen):
        result = Application().launch(ConnectionRequest(str(self.profile())))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "launch_failed")
        self.assertIn("eitaas-remmina", result.error.message)
        popen.assert_not_called()

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.remmina.find_launcher", return_value=LAUNCHER)
    def test_invalid_profile_never_reaches_launcher(self, find_launcher, popen):
        profile = self.profile()
        profile.chmod(0o644)
        result = Application().launch(ConnectionRequest(str(profile)))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "launch_failed")
        popen.assert_not_called()

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.remmina.find_launcher", return_value=LAUNCHER)
    def test_launch_can_be_cancelled(self, find_launcher, popen):
        process = Mock(poll=Mock(return_value=None), returncode=-15)
        process.wait.return_value = -15
        popen.return_value = process
        cancel = threading.Event()

        def progress(event):
            if event.phase == "starting":
                cancel.set()

        result = Application().launch(ConnectionRequest(str(self.profile())), progress, cancel)
        self.assertTrue(result.ok)
        self.assertTrue(result.value.cancelled)
        process.terminate.assert_called_once()
        process.kill.assert_not_called()

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.remmina.find_launcher", return_value=LAUNCHER)
    def test_unresponsive_child_is_killed_after_terminate(self, find_launcher, popen):
        process = Mock(poll=Mock(return_value=None), returncode=-9)
        process.wait.side_effect = [subprocess.TimeoutExpired("eitaas-remmina", 5), -9]
        popen.return_value = process
        cancel = threading.Event()

        def progress(event):
            if event.phase == "starting":
                cancel.set()

        result = Application().launch(ConnectionRequest(str(self.profile())), progress, cancel)
        self.assertTrue(result.ok)
        self.assertTrue(result.value.cancelled)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()

    @patch("eitaas.cli.Application.launch")
    def test_cli_connect_returns_child_exit_status(self, launch):
        launch.return_value = Result(ConnectionResult(3))
        self.assertEqual(main(["connect", "Desktop.rdpw"]), 3)
        launch.assert_called_once_with(ConnectionRequest("Desktop.rdpw"))

    def test_cli_connect_has_no_backend_or_clipboard_flags(self):
        for flag in ("--backend=x11", "--clipboard"):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(["connect", "Desktop.rdpw", flag])

    @patch("eitaas.cli.Application.doctor")
    def test_cli_uses_application_api(self, doctor):
        from eitaas.api import DoctorReport, RemminaBundleSummary

        bundle = RemminaBundleSummary(
            True, True, "/usr/libexec/eitaas-remmina/bin/remmina", "1.4.43", "3.31.0", True
        )
        doctor.return_value = Result(
            DoctorReport("Linux", "x11", True, False, True, {}, bundle, False, True)
        )
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["doctor", "--json"]), 0)


if __name__ == "__main__":
    unittest.main()
