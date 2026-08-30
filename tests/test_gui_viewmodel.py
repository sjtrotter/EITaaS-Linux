import ast
import unittest
from pathlib import Path

from eitaas.api import (
    ApplicationError,
    DoctorReport,
    RemminaBundleSummary,
    SmartcardComponent,
    SmartcardReport,
    StoredProfileSummary,
)
from eitaas_gui import viewmodel


def bundle(launcher=True, client=True):
    return RemminaBundleSummary(launcher, client, "/usr/libexec/x" if client else None, "1.4.43", "3.31.0", None)


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
        identity_broker=True,
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
                         ["client", "session", "pcscd", "reader", "middleware", "broker", "tools"])
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

    def test_broker_absent_is_a_warning_not_a_failure(self):
        rows = viewmodel.readiness_rows(report(identity_broker=False))
        broker = {row.key: row for row in rows}["broker"]
        self.assertEqual(broker.state, viewmodel.WARN)
        self.assertEqual(viewmodel.readiness_summary(report(), rows), "All required checks passed.")

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
    def test_can_connect_requires_launcher_and_profile(self):
        self.assertTrue(viewmodel.can_connect(report(), PROFILE))
        self.assertFalse(viewmodel.can_connect(report(), None))
        self.assertFalse(viewmodel.can_connect(None, PROFILE))
        self.assertFalse(viewmodel.can_connect(report(remmina=bundle(launcher=False)), PROFILE))
        self.assertTrue(viewmodel.can_connect(report(remmina=bundle(client=False)), PROFILE))

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

    def test_exit_text(self):
        self.assertIsNone(viewmodel.exit_text(0, False))
        self.assertEqual(viewmodel.exit_text(130, True), "Connection cancelled.")
        self.assertIn("status 3", viewmodel.exit_text(3, False))


if __name__ == "__main__":
    unittest.main()
