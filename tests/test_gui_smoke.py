"""Headless construction test for the GTK helper.

Skips loudly when PyGObject, GTK 4, Libadwaita, or a display is missing so
CLI-only environments stay green; CI runs it under ``xvfb-run``.
"""

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from eitaas.api import ConnectionResult, ProgressEvent, Result
try:  # ``unittest discover -s tests`` vs ``python -m unittest tests.test_gui_smoke``
    from test_gui_viewmodel import report
except ImportError:
    from tests.test_gui_viewmodel import report

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic.rdpw"
SKIP_REASON = None
try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402
except (ImportError, ValueError) as error:  # pragma: no cover - environment dependent
    SKIP_REASON = f"GTK 4 / Libadwaita bindings unavailable: {error}"
else:
    if not Gtk.init_check():
        SKIP_REASON = "no display available for the GTK smoke test (set DISPLAY or use xvfb-run)"
    elif Gdk.Display.get_default() is None:
        SKIP_REASON = "GTK initialised without a default display"


def pump(seconds: float = 0.5) -> None:
    deadline = GLib.get_monotonic_time() + int(seconds * 1_000_000)
    context = GLib.MainContext.default()
    while GLib.get_monotonic_time() < deadline:
        while context.iteration(False):
            pass


def wait_until(predicate, seconds: float = 5.0) -> None:
    deadline = GLib.get_monotonic_time() + int(seconds * 1_000_000)
    context = GLib.MainContext.default()
    while not predicate():
        if GLib.get_monotonic_time() > deadline:
            raise AssertionError("condition not reached before timeout")
        context.iteration(True)


@unittest.skipIf(SKIP_REASON, SKIP_REASON)
class HelperWindowSmokeTests(unittest.TestCase):
    def setUp(self):
        Adw.init()
        self.home = Path(tempfile.mkdtemp())
        environment = patch.dict(os.environ, {
            "XDG_DATA_HOME": str(self.home / "share"),
            "XDG_CONFIG_HOME": str(self.home / "config"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.doctor = patch("eitaas.api.Application.doctor", return_value=Result(report()))
        self.doctor.start()
        self.addCleanup(self.doctor.stop)
        from eitaas.api import Application
        from eitaas_gui.app import HelperWindow

        self.core = Application()
        self.window = HelperWindow(self.core)
        self.addCleanup(self.window.destroy)
        wait_until(lambda: self.window.report is not None)
        pump(0.2)

    def download(self) -> Path:
        downloads = self.home / "Downloads"
        downloads.mkdir(exist_ok=True)
        path = downloads / "Desktop.rdpw"
        path.write_bytes(FIXTURE.read_bytes())
        path.chmod(0o644)
        return path

    def test_pages_and_readiness_rows(self):
        names = [page.get_name() for page in self.window.stack.get_pages()]
        self.assertEqual(names, ["readiness", "profile", "connect"])
        for name in names:
            self.window.stack.set_visible_child_name(name)
            self.assertEqual(self.window.stack.get_visible_child_name(), name)
        self.assertEqual(len(self.window.readiness_rows), 6)
        self.assertFalse(self.window.connect_button.get_sensitive(), "no profile yet")
        self.assertTrue(self.window.recheck.get_sensitive())

    def test_import_flow_enables_connect_and_launches_default(self):
        source = self.download()
        self.window.import_profile(source)
        wait_until(lambda: [item.name for item in self.window.profiles] == ["Desktop.rdpw"])
        self.assertFalse(source.exists())
        self.assertTrue(self.window.connect_button.get_sensitive())
        self.assertEqual(self.window.profile_rows[0].get_title(), "Desktop.rdpw")

        seen = {}

        def fake_launch(request, on_progress=None, cancel=None):
            seen["request"] = request
            seen["thread"] = threading.get_ident()
            on_progress(ProgressEvent("starting", "Remote desktop client started", cancellable=True))
            cancel.wait(5)
            return Result(ConnectionResult(130, cancelled=True))

        with patch.object(self.core, "launch", side_effect=fake_launch):
            self.window.start_connection()
            wait_until(lambda: self.window.phase_label.get_label() == "Remote desktop client started")
            self.assertFalse(self.window.connect_button.get_visible())
            self.assertTrue(self.window.progress_box.get_visible())
            self.window.cancel_connection()
            wait_until(lambda: self.window.worker is None)
        self.assertIsNone(seen["request"].profile, "launch uses the stored default")
        self.assertNotEqual(seen["thread"], threading.get_ident(), "launch ran on a worker")
        self.assertTrue(self.window.connect_button.get_visible())

    def test_quit_while_running_cancels_then_destroys_without_joining(self):
        self.window.import_profile(self.download())
        wait_until(lambda: len(self.window.profiles) == 1)

        def fake_launch(request, on_progress=None, cancel=None):
            cancel.wait(5)
            return Result(ConnectionResult(130, cancelled=True))

        with patch.object(self.core, "launch", side_effect=fake_launch), \
                patch.object(self.window, "destroy") as destroy:
            self.window.start_connection()
            pump(0.1)
            self.window.request_quit()
            self.assertFalse(self.window.get_visible())
            self.assertTrue(self.window.cancel_event.is_set())
            destroy.assert_not_called()
            wait_until(lambda: self.window.worker is None)
            pump(0.1)
            destroy.assert_called_once()

    def test_launch_error_is_rendered_from_application_error(self):
        self.window.import_profile(self.download())
        wait_until(lambda: len(self.window.profiles) == 1)
        from eitaas.api import ApplicationError

        failure = Result(error=ApplicationError("launch_failed", "eitaas-remmina launcher is not installed",
                                                "Run eitaas doctor and correct failed checks."))
        with patch.object(self.core, "launch", return_value=failure):
            self.window.start_connection()
            wait_until(lambda: self.window.error_label.get_visible())
        self.assertIn("Could not start the connection", self.window.error_label.get_label())
        self.assertIn("Run eitaas doctor", self.window.error_label.get_label())

    def test_offer_import_shows_banner_without_importing(self):
        source = self.download()
        self.window.offer_import(source)
        pump(0.1)
        self.assertEqual(self.window.stack.get_visible_child_name(), "profile")
        self.assertTrue(self.window.import_banner.get_revealed())
        self.assertIn("Desktop.rdpw", self.window.import_banner.get_title())
        self.assertTrue(source.exists(), "no auto-import on open")

    def test_open_web_client_launches_selected_cloud_url(self):
        launched = []
        with patch.object(Gtk.UriLauncher, "launch", lambda launcher, *args: launched.append(launcher.get_uri())):
            self.window.open_web_client()
            self.window.cloud_row.set_selected(self.window.cloud_keys.index("azure_commercial"))
            self.window.open_web_client()
        self.assertEqual(launched, ["https://rdweb.wvd.azure.us/arm/webclient",
                                    "https://client.wvd.microsoft.com/arm/webclient"])
        self.assertEqual(len(self.window.step_rows), 6)

    def test_interactive_widgets_have_accessible_labels(self):
        widgets = [self.window.recheck, self.window.import_button, self.window.connect_button,
                   self.window.cancel_button, self.window.open_client]
        for widget in widgets:
            label = Gtk.Accessible.get_accessible_role(widget)
            self.assertIsNotNone(label)
            self.assertTrue(widget.get_focusable() or widget.get_can_focus(), widget)


    def test_failed_exit_shows_reason_lines_and_copy_button(self):
        self.window.import_profile(self.download())
        wait_until(lambda: len(self.window.profiles) == 1)
        logs = self.home / "state" / "eitaas-remmina" / "logs"
        logs.mkdir(parents=True)
        log = logs / "session-20260830T120000-1.log"
        log.write_text(
            "Connecting to: host\n"
            "(remmina-WARNING) smartcard-auth: discovery-empty: No usable certificates for login.example\n"
            "exit=2\n"
        )
        copied = []
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.home / "state")}), \
                patch.object(self.core, "launch", return_value=Result(ConnectionResult(2, log_path=str(log)))), \
                patch.object(self.window, "copy_text", side_effect=copied.append):
            self.window.start_connection()
            wait_until(lambda: self.window.copy_log_button.get_visible())
            text = self.window.error_label.get_label()
            self.assertIn("status 2", text)
            self.assertIn("discovery-empty", text)
            self.assertIn(str(log), text)
            self.window.copy_log_button.emit("clicked")
        self.assertEqual(copied, [log.read_text()])
        self.assertTrue(self.window.connect_button.get_visible())

        with patch.object(self.core, "launch", return_value=Result(ConnectionResult(0))):
            self.window.start_connection()
            wait_until(lambda: self.window.worker is None)
            pump(0.1)
        self.assertFalse(self.window.copy_log_button.get_visible())
        self.assertFalse(self.window.error_label.get_visible())

        # A clean exit that still logged a smart-card warning shows the diagnostics.
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.home / "state")}), \
                patch.object(self.core, "launch",
                             return_value=Result(ConnectionResult(0, log_path=str(log), log_warnings=1))):
            self.window.start_connection()
            wait_until(lambda: self.window.copy_log_button.get_visible())
        self.assertIn("discovery-empty", self.window.error_label.get_label())


if __name__ == "__main__":
    unittest.main()
