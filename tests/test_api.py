import unittest
import threading
from unittest.mock import patch

from eitaas.api import Application


class ApplicationAPITests(unittest.TestCase):
    @patch("eitaas.api.smartcard.status")
    @patch("eitaas.api.doctor.report")
    def test_doctor_includes_smartcard_readiness(self, report, status):
        report.return_value = {
            "platform": "Linux",
            "session_type": "wayland",
            "display": True,
            "wayland_display": True,
            "pcsc_socket": True,
            "tools": {},
            "remmina": {
                "launcher": True,
                "client": False,
                "client_path": None,
                "remmina_version": "unknown",
                "freerdp_version": "unknown",
                "sso_mib": None,
            },
            "identity_broker": False,
        }
        status.return_value = {
            "reader": {"available": True, "ok": True, "summary": "command completed"}
        }
        result = Application().doctor()
        self.assertTrue(result.ok)
        self.assertTrue(result.value.smartcard.ready)
        self.assertFalse(result.value.ready)
        self.assertTrue(result.value.remmina.launcher)
        self.assertFalse(result.value.remmina.client)
        self.assertIsNone(result.value.remmina.sso_mib)

    @patch("eitaas.api.smartcard.status")
    def test_smartcard_async_runs_on_worker(self, status):
        caller = threading.get_ident()
        worker = []

        def result():
            worker.append(threading.get_ident())
            return {}

        status.side_effect = result
        report = Application().smartcard_status_async().result(timeout=2)
        self.assertTrue(report.ok)
        self.assertNotEqual(worker, [caller])

    @patch("eitaas.api.inspect_profile")
    def test_errors_are_redacted_at_boundary(self, inspect):
        inspect.side_effect = ValueError("code=very-secret-value")
        result = Application().inspect_profile("example.rdpw")
        self.assertFalse(result.ok)
        self.assertNotIn("very-secret-value", result.error.message)

    def test_profile_result_uses_basename_only(self):
        with patch("eitaas.api.inspect_profile") as inspect:
            inspect.return_value = {
                "size": 1,
                "mode": "0600",
                "cloud": "azure_government",
                "fields": [],
            }
            result = Application().inspect_profile("/sensitive/location/example.rdpw")
        self.assertTrue(result.ok)
        self.assertEqual(result.value.display_name, "example.rdpw")
        self.assertFalse(hasattr(result.value, "path"))

    def test_diagnostics_do_not_expose_profile_path(self):
        with patch("eitaas.api.inspect_profile") as inspect:
            inspect.return_value = {
                "size": 1,
                "mode": "0600",
                "cloud": "azure_government",
                "fields": [],
            }
            report = Application().diagnostics("/sensitive/location/example.rdpw")
        self.assertTrue(report.ok)
        self.assertEqual(report.value.profile.display_name, "example.rdpw")
        self.assertNotIn("/sensitive/location", str(report.value))


if __name__ == "__main__":
    unittest.main()


class LaunchLoggingTests(unittest.TestCase):
    """``launch`` against a real (fake) child: output lands redacted in the session log."""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path

        self.root = Path(tempfile.mkdtemp(prefix="eitaas-launch-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state = self.root / "state"
        env = patch.dict("os.environ", {"XDG_STATE_HOME": str(self.state)})
        env.start()
        self.addCleanup(env.stop)
        self.profile = self.root / "Desktop.rdpw"
        self.profile.write_bytes((Path(__file__).parent / "fixtures" / "synthetic.rdpw").read_bytes())
        self.profile.chmod(0o600)

    def launcher(self, script: str):
        path = self.root / "eitaas-remmina"
        path.write_text("#!/bin/sh\n" + script)
        path.chmod(0o700)
        return patch("eitaas.api.remmina.find_launcher", return_value=str(path))

    def test_child_output_is_logged_redacted_with_exit_code(self):
        from pathlib import Path

        from eitaas import remmina
        from eitaas.api import ConnectionRequest

        script = (
            "echo 'Connecting to: host' >&2\n"
            "echo '(remmina-WARNING) smartcard-auth: discovery-empty: none for login.example' >&2\n"
            "echo 'id_token=synthetic-id-token-value'\n"
            "echo \"argv=$*\" >&2\n"
            "exit 2\n"
        )
        with self.launcher(script), patch("eitaas.api.remmina.running_remmina_instances", return_value=1):
            result = Application().launch(ConnectionRequest(str(self.profile)))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value.exit_code, 2)
        self.assertFalse(result.value.cancelled)
        self.assertTrue(result.value.log_path.startswith(str(self.state / "eitaas-remmina" / "logs")))
        text = Path(result.value.log_path).read_text(encoding="utf-8")
        self.assertIn("remmina instances already running: 1", text)
        self.assertIn("profile=Desktop.rdpw", text)
        self.assertIn("smartcard-auth: discovery-empty", text)
        self.assertIn("id_token=<redacted>", text)
        self.assertNotIn("synthetic-id-token-value", text)
        self.assertIn(f"argv={self.profile}", text, "stdout and stderr both reach the log")
        self.assertTrue(text.endswith("exit=2\n"))
        self.assertEqual(remmina.latest_session_log(), result.value.log_path)

        summary = Application().session_log(result.value.log_path)
        self.assertTrue(summary.ok, summary.error)
        self.assertEqual(summary.value.path, result.value.log_path)
        self.assertEqual(len(summary.value.reason_lines), 1)
        self.assertIn("discovery-empty", summary.value.reason_lines[0])
        self.assertEqual(summary.value.text, text)

    def test_warning_lines_are_counted_even_on_a_clean_exit(self):
        from eitaas.api import ConnectionRequest

        script = (
            "echo '(remmina:1): remmina-WARNING **: (show_error) - smartcard-auth: discovery-empty: none' >&2\n"
            "echo '(remmina:1): remmina-DEBUG: smartcard-auth: discovery-start' >&2\n"
            "exit 0\n"
        )
        with self.launcher(script):
            result = Application().launch(ConnectionRequest(str(self.profile)))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value.exit_code, 0)
        self.assertEqual(result.value.log_warnings, 1)
        with self.launcher("exit 0\n"):
            self.assertEqual(Application().launch(ConnectionRequest(str(self.profile))).value.log_warnings, 0)

    def test_session_log_serves_only_files_in_the_log_directory(self):
        outside = self.root / "session-outside.log"
        outside.write_text("secret")
        result = Application().session_log(str(outside))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "session_log_failed")
        logs = self.state / "eitaas-remmina" / "logs"
        logs.mkdir(parents=True)
        other = logs / "notes.txt"
        other.write_text("x")
        self.assertFalse(Application().session_log(str(other)).ok)

    def test_launch_still_works_when_the_log_cannot_be_created(self):
        from eitaas.api import ConnectionRequest

        with self.launcher("exit 0\n"), patch("eitaas.api.remmina.SessionLog.open", side_effect=OSError("ro")):
            result = Application().launch(ConnectionRequest(str(self.profile)))
        self.assertTrue(result.ok)
        self.assertEqual(result.value.exit_code, 0)
        self.assertIsNone(result.value.log_path)

    def test_cancel_terminates_child_and_closes_log(self):
        from pathlib import Path

        from eitaas.api import ConnectionRequest

        cancel = threading.Event()
        timer = threading.Timer(0.5, cancel.set)
        timer.start()
        self.addCleanup(timer.cancel)
        with self.launcher("echo started >&2\nexec sleep 30\n"):
            result = Application().launch(ConnectionRequest(str(self.profile)), cancel=cancel)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.value.cancelled)
        self.assertEqual(result.value.exit_code, 130)
        text = Path(result.value.log_path).read_text(encoding="utf-8")
        self.assertIn("started", text)
        self.assertTrue(text.endswith("exit=130\n"), text)
