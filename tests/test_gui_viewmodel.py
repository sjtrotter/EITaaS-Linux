import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eitaas.api import (
    ApplicationError,
    DoctorReport,
    RemminaBundleSummary,
    SmartcardComponent,
    SmartcardReport,
    StoredProfileSummary,
)
from eitaas_gui import state, viewmodel


def bundle(launcher=True, client=True):
    return RemminaBundleSummary(launcher, client, "/usr/libexec/x" if client else None, "1.4.43", "3.30.0")


def smartcard(pcscd=True, reader=True, middleware=True, available=True):
    def component(name, ok):
        return SmartcardComponent(name, available, ok and available, "command completed" if ok else "command failed (exit 1)")

    components = (component("pcscd", pcscd), component("reader", reader), component("middleware", middleware))
    return SmartcardReport(components, all(item.ok for item in components))


def report(**overrides):
    values = dict(
        platform="Linux",
        session_type="wayland",
        display=True,
        wayland_display=True,
        pcsc_socket=True,
        tools={"pcsc_scan": True, "pkcs11-tool": True, "systemctl": True, "openssl": True, "certutil": True},
        remmina=bundle(),
        ready=True,
        smartcard=smartcard(),
    )
    values.update(overrides)
    return DoctorReport(**values)


PROFILE = StoredProfileSummary("Desktop.rdpw", "azure_government", 192, "0600", "2026-08-30T12:00:00", True)


class ReadinessRowTests(unittest.TestCase):
    def test_viewmodel_imports_no_toolkit(self):
        tree = ast.parse(Path(viewmodel.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertNotIn("gi", imported, "viewmodel must stay toolkit-free")

    def test_all_ready(self):
        rows = viewmodel.readiness_rows(report())
        self.assertEqual([row.key for row in rows],
                         ["client", "session", "pcscd", "reader", "middleware", "tools"])
        self.assertTrue(all(row.state == viewmodel.OK for row in rows))
        self.assertTrue(all(row.hint is None and row.command is None for row in rows))
        self.assertEqual(viewmodel.readiness_summary(report(), rows), "All required checks passed.")

    def test_missing_client_names_package(self):
        rows = {row.key: row for row in viewmodel.readiness_rows(report(remmina=bundle(False, False)))}
        self.assertEqual(rows["client"].state, viewmodel.FAIL)
        self.assertIn("eitaas-remmina", rows["client"].hint)
        self.assertIn("Bundled remote desktop client", viewmodel.readiness_summary(report(), list(rows.values())))

    def test_pcscd_down_gives_copyable_command(self):
        rows = {row.key: row for row in viewmodel.readiness_rows(report(pcsc_socket=False, smartcard=smartcard(pcscd=False)))}
        self.assertEqual(rows["pcscd"].state, viewmodel.FAIL)
        self.assertEqual(rows["pcscd"].command, "systemctl enable --now pcscd.socket")

    def test_reader_check_is_labelled_truthfully(self):
        row = {row.key: row for row in viewmodel.readiness_rows(report())}["reader"]
        self.assertIn("does not prove a card is inserted", row.detail)
        missing = {row.key: row for row in viewmodel.readiness_rows(report(smartcard=smartcard(available=False)))}
        self.assertEqual(missing["reader"].state, viewmodel.UNKNOWN)
        self.assertIn("pcsc-tools", missing["reader"].hint)
        self.assertIn("opensc", missing["middleware"].hint)

    def test_missing_tools_map_to_packages(self):
        tools = {"pcsc_scan": False, "certutil": False, "openssl": True}
        row = {row.key: row for row in viewmodel.readiness_rows(report(tools=tools))}["tools"]
        self.assertEqual(row.state, viewmodel.WARN)
        self.assertIn("pcsc-tools", row.hint)
        self.assertIn("nss-tools", row.hint)

    def test_error_yields_single_unknown_row(self):
        rows = viewmodel.readiness_rows(None, ApplicationError("doctor_failed", "boom"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].state, viewmodel.UNKNOWN)
        self.assertEqual(rows[0].detail, "boom")

    def test_states_have_distinct_icons_and_labels(self):
        states = (viewmodel.OK, viewmodel.WARN, viewmodel.FAIL, viewmodel.UNKNOWN)
        self.assertEqual(len({viewmodel.state_icon(state) for state in states}), 4)
        self.assertEqual(len({viewmodel.state_label(state) for state in states}), 4)


class ConnectTests(unittest.TestCase):
    def test_can_connect_disabled_only_on_hard_failures(self):
        self.assertTrue(viewmodel.can_connect(report(), PROFILE))
        self.assertFalse(viewmodel.can_connect(report(), None))
        self.assertFalse(viewmodel.can_connect(None, PROFILE))
        self.assertFalse(viewmodel.can_connect(report(remmina=bundle(launcher=False)), PROFILE))
        self.assertFalse(viewmodel.can_connect(report(remmina=bundle(client=False)), PROFILE))
        # Warnings (missing diagnostic tools) never disable Connect.
        self.assertTrue(viewmodel.can_connect(report(tools={"pcsc_scan": False}), PROFILE))
        # Nor do soft smart-card failures; the client prompts in its own window.
        self.assertTrue(viewmodel.can_connect(
            report(pcsc_socket=False, smartcard=smartcard(pcscd=False)), PROFILE))

    def test_description_names_profile_and_handoff(self):
        text = viewmodel.connect_description(PROFILE, "All required checks passed.")
        self.assertIn("Desktop.rdpw", text)
        self.assertIn("PIN", text)
        self.assertIn("Import a profile", viewmodel.connect_description(None, ""))

    def test_profile_subtitle_has_no_field_values(self):
        subtitle = viewmodel.profile_subtitle(PROFILE)
        self.assertIn("Azure US Government", subtitle)
        self.assertIn("0600", subtitle)
        self.assertIn("2026-08-30 12:00:00", subtitle)

    def test_error_text_uses_stable_title_and_recovery(self):
        title, body = viewmodel.error_text(ApplicationError("launch_failed", "redacted", "Run eitaas doctor"))
        self.assertEqual(title, "Could not start the connection")
        self.assertIn("redacted", body)
        self.assertIn("Run eitaas doctor", body)
        self.assertEqual(viewmodel.error_text(ApplicationError("other", "x"))[0], "Something went wrong")

    def test_web_client_urls_are_the_two_public_clients_only(self):
        self.assertEqual(viewmodel.web_client_url("azure_government"), "https://rdweb.wvd.azure.us/arm/webclient")
        self.assertEqual(viewmodel.web_client_url("azure_commercial"), "https://client.wvd.microsoft.com/arm/webclient")
        self.assertEqual(viewmodel.DEFAULT_WEB_CLIENT, "azure_government")
        with self.assertRaises(KeyError):
            viewmodel.web_client_url("https://evil.example")
        self.assertEqual(len(viewmodel.EXPORT_STEPS), 6)
        self.assertTrue(all("CAC" not in text for text in (*viewmodel.EXPORT_STEPS, viewmodel.WHY_PROFILE)))

    def test_exit_text(self):
        self.assertIsNone(viewmodel.exit_text(0, False))
        self.assertEqual(viewmodel.exit_text(130, True), "Connection cancelled.")
        self.assertIn("status 3", viewmodel.exit_text(3, False))


if __name__ == "__main__":
    unittest.main()


class DiagnosticTextTests(unittest.TestCase):
    def test_diagnostic_text_lists_reason_lines_and_log_path(self):
        lines = ("(remmina-WARNING) smartcard-auth: origin-rejected (proxy-challenge)",)
        text = viewmodel.diagnostic_text(2, lines, "/home/u/.local/state/eitaas-remmina/logs/session-1.log")
        self.assertIn("status 2", text)
        self.assertIn("origin-rejected", text)
        self.assertIn("Diagnostic log: /home/u/.local/state/eitaas-remmina/logs/session-1.log", text)

    def test_diagnostic_text_for_a_clean_exit_with_warnings(self):
        text = viewmodel.diagnostic_text(0, ("smartcard-auth: discovery-empty",), None)
        self.assertIn("exited normally but reported smart-card warnings", text)
        self.assertIn("discovery-empty", text)

    def test_diagnostic_text_without_lines_or_log(self):
        text = viewmodel.diagnostic_text(1, (), None)
        self.assertIn("status 1", text)
        self.assertIn("no smart-card diagnostic lines", text)
        self.assertNotIn("Diagnostic log:", text)


class ReadinessMarkerTests(unittest.TestCase):
    def test_hash_is_stable_and_state_sensitive(self):
        rows = viewmodel.readiness_rows(report())
        again = viewmodel.readiness_rows(report())
        self.assertEqual(viewmodel.readiness_hash(rows), viewmodel.readiness_hash(again))
        changed = viewmodel.readiness_rows(report(tools={"pcsc_scan": False}))
        self.assertNotEqual(viewmodel.readiness_hash(rows), viewmodel.readiness_hash(changed))

    def test_readiness_passed_allows_warnings_only(self):
        self.assertTrue(viewmodel.readiness_passed(report(), viewmodel.readiness_rows(report())))
        warn = report(tools={"pcsc_scan": False})
        self.assertTrue(viewmodel.readiness_passed(warn, viewmodel.readiness_rows(warn)))
        fail = report(remmina=bundle(False, False))
        self.assertFalse(viewmodel.readiness_passed(fail, viewmodel.readiness_rows(fail)))
        self.assertFalse(viewmodel.readiness_passed(None, viewmodel.readiness_rows(None)))

    def test_marker_document_round_trips(self):
        marker = viewmodel.ReadinessMarker("2026-08-30T12:00:00+00:00", "ab" * 32)
        self.assertEqual(viewmodel.parse_marker(viewmodel.marker_document(marker)), marker)

    def test_parse_marker_rejects_anything_unexpected(self):
        for text in (
            "",
            "not json",
            "[]",
            '"a string"',
            "{}",
            '{"version": 99, "timestamp": "t", "doctor_hash": "%s"}' % ("ab" * 32),
            '{"version": true, "timestamp": "t", "doctor_hash": "%s"}' % ("ab" * 32),
            '{"version": 1, "timestamp": 5, "doctor_hash": "%s"}' % ("ab" * 32),
            '{"version": 1, "timestamp": "t", "doctor_hash": ""}',
            '{"version": 1, "timestamp": "t", "doctor_hash": "h"}',
            '{"version": 1, "timestamp": "t", "doctor_hash": "%s"}' % ("AB" * 32),
            '{"version": 1, "timestamp": "t", "doctor_hash": "%s"}' % ("ab" * 31),
            '{"version": 1, "timestamp": "t"}',
        ):
            self.assertIsNone(viewmodel.parse_marker(text), text)

    def test_startup_page_needs_marker_and_default_profile(self):
        marker = viewmodel.ReadinessMarker("t", "h")
        self.assertEqual(viewmodel.startup_page(marker, PROFILE), "connect")
        self.assertEqual(viewmodel.startup_page(None, PROFILE), "readiness")
        self.assertEqual(viewmodel.startup_page(marker, None), "readiness")
        self.assertEqual(viewmodel.startup_page(None, None), "readiness")

    def test_regression_requires_marker_report_and_hard_failure(self):
        marker = viewmodel.ReadinessMarker("t", "h")
        failing = report(pcsc_socket=False, smartcard=smartcard(pcscd=False))
        fail_rows = viewmodel.readiness_rows(failing)
        self.assertTrue(viewmodel.regression(marker, failing, fail_rows))
        warning = report(tools={"pcsc_scan": False})
        self.assertFalse(viewmodel.regression(marker, warning, viewmodel.readiness_rows(warning)))
        self.assertFalse(viewmodel.regression(None, failing, fail_rows))
        error_rows = viewmodel.readiness_rows(None, ApplicationError("doctor_failed", "boom"))
        self.assertFalse(viewmodel.regression(marker, None, error_rows),
                         "a doctor error is not a regression")

    def test_regression_text_names_the_failing_checks(self):
        failing = report(pcsc_socket=False, smartcard=smartcard(pcscd=False))
        heading, body = viewmodel.regression_text(viewmodel.readiness_rows(failing))
        self.assertEqual(heading, "Readiness has changed")
        self.assertIn("Smart-card service", body)
        self.assertIn("Readiness page", body)


class MarkerStoreTests(unittest.TestCase):
    def setUp(self):
        self.state_home = Path(tempfile.mkdtemp(prefix="eitaas-gui-state-"))
        environment = patch.dict(os.environ, {"XDG_STATE_HOME": str(self.state_home)})
        environment.start()
        self.addCleanup(environment.stop)

    def test_record_pass_writes_private_marker(self):
        marker = state.record_pass("a" * 64)
        path = state.marker_path()
        self.assertEqual(path, self.state_home / "eitaas-gui" / "last-readiness-pass.json")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(state.read_marker(), marker)
        self.assertEqual(marker.doctor_hash, "a" * 64)

    def test_record_pass_restores_mode_on_an_existing_file(self):
        state.record_pass("a" * 64)
        state.marker_path().chmod(0o644)
        state.record_pass("b" * 64)
        self.assertEqual(state.marker_path().stat().st_mode & 0o777, 0o600)

    def test_read_marker_rejects_garbage_symlinks_and_oversize(self):
        self.assertIsNone(state.read_marker(), "missing file reads as no pass")
        directory = state.state_dir()
        directory.mkdir(parents=True)
        path = state.marker_path()
        path.write_text("not json")
        self.assertIsNone(state.read_marker())
        path.unlink()
        path.symlink_to(directory / "elsewhere")
        self.assertIsNone(state.read_marker(), "symlinks are refused")
        path.unlink()
        path.write_text("{}" + " " * 5000)
        self.assertIsNone(state.read_marker(), "oversized files are refused")

    def test_clear_marker_is_idempotent(self):
        state.clear_marker()
        state.record_pass("b" * 64)
        state.clear_marker()
        self.assertIsNone(state.read_marker())
        state.clear_marker()
