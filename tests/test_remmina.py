import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eitaas import doctor, remmina

MANIFEST = {"sources": {"remmina": {"version": "1.4.43"}, "freerdp": {"version": "3.30.0"}}}


def make_prefix(case: unittest.TestCase, *, client: bool = True) -> Path:
    """Build a fake private prefix with an optional bin/remmina."""
    root = Path(tempfile.mkdtemp(prefix="eitaas-remmina-"))
    case.addCleanup(shutil.rmtree, root, True)
    if client:
        binary = root / "bin" / "remmina"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"\x7fELF")
    return root


class RemminaBundleTests(unittest.TestCase):
    def test_launcher_prefers_packaged_path_then_search_path(self):
        packaged = make_prefix(self) / "eitaas-remmina"
        packaged.write_text("#!/bin/sh\n")
        packaged.chmod(0o755)
        with patch("eitaas.remmina.INSTALLED_LAUNCHER", packaged), patch(
            "eitaas.remmina.shutil.which", return_value="/opt/bin/eitaas-remmina"
        ) as which:
            self.assertEqual(remmina.find_launcher(), str(packaged))
            which.assert_not_called()
        with patch("eitaas.remmina.INSTALLED_LAUNCHER", packaged.with_name("missing")), patch(
            "eitaas.remmina.shutil.which", return_value="/opt/bin/eitaas-remmina"
        ) as which:
            self.assertEqual(remmina.find_launcher(), "/opt/bin/eitaas-remmina")
        which.assert_called_once_with("eitaas-remmina")

    def test_launch_profile_requires_rdpw_suffix(self):
        root = make_prefix(self)
        for suffix, ok in ((".rdpw", True), (".RDPW", True), (".rdp", False)):
            profile = root / f"desktop{suffix}"
            profile.write_bytes(b"full address:s:synthetic.wvd.azure.us\n")
            profile.chmod(0o600)
            if ok:
                self.assertEqual(remmina.validate_launch_profile(profile), profile)
            else:
                with self.assertRaisesRegex(ValueError, "rdpw"):
                    remmina.validate_launch_profile(profile)

    def test_private_client_uses_first_existing_candidate(self):
        first = make_prefix(self) / "bin" / "remmina"
        second = make_prefix(self) / "bin" / "remmina"
        missing = make_prefix(self, client=False) / "bin" / "remmina"
        with patch("eitaas.remmina.PRIVATE_CLIENTS", (first, second)):
            self.assertEqual(remmina.private_client(), first)
        with patch("eitaas.remmina.PRIVATE_CLIENTS", (missing, second)):
            self.assertEqual(remmina.private_client(), second)
        with patch("eitaas.remmina.PRIVATE_CLIENTS", (missing,)):
            self.assertIsNone(remmina.private_client())

    def test_pinned_versions_come_from_installed_manifest(self):
        manifest = make_prefix(self) / "sources.json"
        manifest.write_text(json.dumps(MANIFEST))
        self.assertEqual(remmina.pinned_versions(manifest), {"remmina": "1.4.43", "freerdp": "3.30.0"})

    def test_pinned_versions_fall_back_to_unknown(self):
        unknown = {"remmina": "unknown", "freerdp": "unknown"}
        manifest = make_prefix(self) / "sources.json"
        self.assertEqual(remmina.pinned_versions(manifest), unknown)
        manifest.write_text("not json")
        self.assertEqual(remmina.pinned_versions(manifest), unknown)
        manifest.write_text(json.dumps({"sources": {"remmina": {"version": ""}}}))
        self.assertEqual(remmina.pinned_versions(manifest), unknown)


class DoctorTests(unittest.TestCase):
    def report(self, launcher: str | None, prefix: Path | None, manifest: Path) -> dict:
        clients = (prefix / "bin" / "remmina",) if prefix else ()
        with patch("eitaas.remmina.find_launcher", return_value=launcher), patch(
            "eitaas.remmina.PRIVATE_CLIENTS", clients
        ), patch("eitaas.remmina.INSTALLED_MANIFEST", manifest), patch(
            "eitaas.doctor.shutil.which", return_value=None
        ):
            return doctor.report()

    def test_report_describes_installed_bundle(self):
        root = make_prefix(self)
        manifest = root / "sources.json"
        manifest.write_text(json.dumps(MANIFEST))
        data = self.report("/usr/bin/eitaas-remmina", root, manifest)
        self.assertEqual(
            data["remmina"],
            {
                "launcher": True,
                "client": True,
                "client_path": str(root / "bin" / "remmina"),
                "remmina_version": "1.4.43",
                "freerdp_version": "3.30.0",
            },
        )
        self.assertNotIn("freerdp", data)
        self.assertNotIn("identity_broker", data)
        self.assertTrue(doctor.healthy(data))

    def test_missing_launcher_or_client_is_unhealthy(self):
        root = make_prefix(self)
        manifest = root / "sources.json"
        self.assertFalse(doctor.healthy(self.report(None, root, manifest)))
        data = self.report("/usr/bin/eitaas-remmina", None, manifest)
        self.assertFalse(doctor.healthy(data))
        self.assertEqual(data["remmina"]["remmina_version"], "unknown")
        self.assertIsNone(data["remmina"]["client_path"])
        self.assertNotIn("sso_mib", data["remmina"])
        self.assertFalse(doctor.healthy({}))


if __name__ == "__main__":
    unittest.main()


class SessionLogTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="eitaas-logs-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.logs = self.root / "state" / "eitaas-remmina" / "logs"

    def test_log_is_private_redacted_and_records_exit(self):
        log = remmina.SessionLog.open(self.logs)
        self.assertEqual(self.logs.stat().st_mode & 0o777, 0o700)
        self.assertEqual(log.path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(log.path.name.startswith("session-") and log.path.name.endswith(".log"))
        log.write("access_token=synthetic-access-token\n")
        log.write("(rdp) smartcard-auth: discovery-empty: No usable certificates for login.example\r\n")
        log.write("https://login.example/authorize?code=SECRET&state=abc")
        log.write("(remmina:1): remmina-WARNING **: smartcard-auth: load-timeout: Loading timed out")
        log.close(2)
        self.assertEqual(log.warnings, 1, "only lines carrying both smartcard-auth and WARNING count")
        text = log.path.read_text()
        self.assertNotIn("synthetic-access-token", text)
        self.assertNotIn("SECRET", text)
        self.assertIn("access_token=<redacted>", text)
        self.assertIn("smartcard-auth: discovery-empty", text)
        self.assertIn("code=%3Credacted%3E", text)
        self.assertTrue(text.endswith("exit=2\n"))
        self.assertNotIn("\r", text)

    def test_cap_truncates_once_and_still_records_exit(self):
        log = remmina.SessionLog.open(self.logs, limit=200)
        for _ in range(50):
            log.write("x" * 40)
        log.close(1)
        lines = log.path.read_text().splitlines()
        self.assertLessEqual(log.path.stat().st_size, 200 + len(remmina.SESSION_LOG_TRUNCATED) + 8)
        self.assertEqual(lines.count(remmina.SESSION_LOG_TRUNCATED), 1)
        self.assertEqual(lines[-1], "exit=1")
        self.assertEqual(lines[-2], remmina.SESSION_LOG_TRUNCATED)

    def test_rotation_keeps_the_newest_logs(self):
        from datetime import datetime, timedelta

        start = datetime(2026, 8, 30, 12, 0, 0)
        paths = []
        import os

        old = 1_000_000_000
        for index in range(7):
            log = remmina.SessionLog.open(self.logs, keep=5, now=start + timedelta(seconds=index))
            log.close(0)
            os.utime(log.path, (old + index, old + index))  # finished long ago
            paths.append(log.path)
        remaining = sorted(self.logs.iterdir())
        self.assertEqual(remaining, sorted(paths[-5:]))
        self.assertEqual(remmina.latest_session_log(self.logs), str(paths[-1]))
        # A log younger than the active window is never pruned, even when it is the oldest.
        os.utime(paths[-5], None)
        remmina.SessionLog.open(self.logs, keep=5, now=start + timedelta(seconds=10)).close(0)
        self.assertIn(paths[-5], list(self.logs.iterdir()))

    def test_two_launches_in_the_same_instant_get_distinct_files(self):
        from datetime import datetime

        now = datetime(2026, 8, 30, 12, 0, 0, 123456)
        first = remmina.SessionLog.open(self.logs, now=now)
        second = remmina.SessionLog.open(self.logs, now=now)
        self.assertNotEqual(first.path, second.path)
        self.assertIn("120000.123456", first.path.name)
        first.close(0)
        second.close(0)

    def test_latest_session_log_without_directory_is_none(self):
        self.assertIsNone(remmina.latest_session_log(self.logs))
        with patch.dict("os.environ", {"XDG_STATE_HOME": str(self.root / "state")}):
            self.assertEqual(remmina.session_log_dir(), self.logs)
            self.assertIsNone(remmina.latest_session_log())

    def test_writes_after_close_and_failures_never_raise(self):
        log = remmina.SessionLog.open(self.logs)
        log.close(0)
        log.write("late line")
        self.assertEqual(log.path.read_text(), "exit=0\n")
        broken = remmina.SessionLog(self.logs / "broken.log", Mock(write=Mock(side_effect=OSError)))
        broken.write("line")
        broken.close(3)

    def test_reason_lines_select_codes_and_warnings(self):
        text = "\n".join(
            [
                "Connecting to: host",
                "(remmina-WARNING) smartcard-auth: origin-rejected (proxy-challenge)",
                "noise",
                "(rdp) smartcard-auth: discovery-finished (tokens=1 certificates=4 label-filter kept=2 dropped=2)",
                "(remmina-WARNING) smartcard-auth: discovery-empty: No usable certificates",
                "exit=2",
            ]
        )
        lines = remmina.reason_lines(text, limit=2)
        self.assertEqual(len(lines), 2)
        self.assertIn("discovery-finished", lines[0])
        self.assertIn("discovery-empty", lines[1])
        self.assertEqual(remmina.reason_lines(""), ())

    def test_running_instances_scans_proc_comm(self):
        proc = self.root / "proc"
        for pid, name in (("1", "systemd"), ("42", "remmina"), ("43", "remmina"), ("44", "remmina-x")):
            (proc / pid).mkdir(parents=True)
            (proc / pid / "comm").write_text(name + "\n")
        real_open = open

        def fake_open(path, *args, **kwargs):
            return real_open(str(path).replace("/proc/", f"{proc}/", 1), *args, **kwargs)

        with patch("eitaas.remmina.os.listdir", return_value=["1", "42", "43", "44", "self"]), \
                patch("builtins.open", fake_open):
            self.assertEqual(remmina.running_remmina_instances(), 2)
        with patch("eitaas.remmina.os.listdir", side_effect=OSError):
            self.assertEqual(remmina.running_remmina_instances(), 0)
