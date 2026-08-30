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
    from test_gui_viewmodel import bundle, report, smartcard
except ImportError:
    from tests.test_gui_viewmodel import bundle, report, smartcard

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic.rdpw"
SKIP_REASON = None
try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402
# AttributeError covers an incomplete `gi` (a build root that has the
# namespace but not PyGObject itself).
except (ImportError, ValueError, AttributeError) as error:  # pragma: no cover - environment dependent
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
            "XDG_STATE_HOME": str(self.home / "state"),
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

    def test_first_run_stays_on_readiness(self):
        from eitaas_gui import state

        self.assertEqual(self.window.stack.get_visible_child_name(), "readiness")
        self.assertIsNotNone(state.read_marker(), "a passing check records the marker")

    def test_startup_lands_on_connect_with_marker_and_default_profile(self):
        from eitaas_gui import state, viewmodel
        from eitaas_gui.app import HelperWindow

        self.window.import_profile(self.download())
        wait_until(lambda: len(self.window.profiles) == 1)
        state.record_pass(viewmodel.readiness_hash(self.window.rows))
        window = HelperWindow(self.core)
        self.addCleanup(window.destroy)
        wait_until(lambda: window.stack.get_visible_child_name() == "connect")
        wait_until(lambda: window.report is not None)
        pump(0.1)
        self.assertIsNone(window.regression_dialog)
        self.assertTrue(window.connect_button.get_sensitive())
        self.assertIsNotNone(state.read_marker(), "the background pass keeps the marker")

    def test_marker_without_default_profile_stays_on_readiness(self):
        from eitaas_gui import state
        from eitaas_gui.app import HelperWindow

        state.record_pass("c" * 64)
        window = HelperWindow(self.core)
        self.addCleanup(window.destroy)
        wait_until(lambda: window.report is not None and not window._startup_to_connect)
        pump(0.1)
        self.assertEqual(window.stack.get_visible_child_name(), "readiness")

    def test_stale_doctor_completion_is_discarded(self):
        from eitaas.api import Result
        from eitaas_gui import state

        self.assertIsNotNone(state.read_marker(), "setUp run recorded a pass")
        passing_report = self.window.report
        stale = Result(report(remmina=bundle(False, False)))
        self.window._readiness_done(self.window._doctor_generation - 1, stale)
        self.assertIs(self.window.report, passing_report, "stale completion must not land")
        self.assertIsNotNone(state.read_marker(), "stale failure must not clear the marker")
        self.assertIsNotNone(self.window.marker)

    def test_regression_during_launch_defers_dialog(self):
        from eitaas.api import Result
        from eitaas_gui import state

        self.window.import_profile(self.download())
        wait_until(lambda: len(self.window.profiles) == 1)
        self.window.stack.set_visible_child_name("connect")
        self.assertIsNotNone(self.window.marker, "setUp run recorded a pass")

        def fake_launch(request, on_progress=None, cancel=None):
            cancel.wait(5)
            return Result(ConnectionResult(130, cancelled=True))

        failing = Result(report(pcsc_socket=False, smartcard=smartcard(pcscd=False)))
        with patch.object(self.core, "launch", side_effect=fake_launch):
            self.window.start_connection()
            pump(0.1)
            self.window._readiness_done(self.window._doctor_generation, failing)
            self.assertIsNone(self.window.regression_dialog, "dialog deferred while launching")
            self.assertIsNone(state.read_marker(), "the marker is still cleared at once")
            self.window.cancel_connection()
            wait_until(lambda: self.window.worker is None)
            pump(0.1)
        wait_until(lambda: self.window.regression_dialog is not None)
        dialog = self.window.regression_dialog
        # A fresh pass recorded while the dialog stood open survives dismissal.
        self.window.marker = state.record_pass("d" * 64)
        self.window._regression_dismissed(dialog, "review")
        self.assertEqual(self.window.stack.get_visible_child_name(), "readiness")
        self.assertIsNotNone(state.read_marker(), "dismissal must not delete a fresh pass")
        dialog.force_close()
        pump(0.1)

    def test_regression_dialog_switches_to_readiness_and_clears_marker(self):
        from eitaas.api import Result
        from eitaas_gui import state, viewmodel
        from eitaas_gui.app import HelperWindow

        self.window.import_profile(self.download())
        wait_until(lambda: len(self.window.profiles) == 1)
        state.record_pass(viewmodel.readiness_hash(self.window.rows))
        release = threading.Event()

        def failing_doctor():
            release.wait(5)
            return Result(report(pcsc_socket=False, smartcard=smartcard(pcscd=False)))

        with patch("eitaas.api.Application.doctor", side_effect=failing_doctor):
            window = HelperWindow(self.core)
            self.addCleanup(window.destroy)
            wait_until(lambda: window.stack.get_visible_child_name() == "connect")
            release.set()
            wait_until(lambda: window.regression_dialog is not None)
            dialog = window.regression_dialog
            self.assertEqual(dialog.get_heading(), "Readiness has changed")
            self.assertEqual(dialog.get_close_response(), "review")
            self.assertEqual(dialog.get_default_response(), "review")
            self.assertTrue(window.connect_button.get_sensitive(),
                            "a smart-card failure is not a hard failure for Connect")
            self.assertIsNone(state.read_marker(), "a regression forgets the recorded pass")
            # Dismiss through the app's own handler, synchronously. Emitting the
            # response via dialog.close() depends on the dialog being mapped,
            # which never happens on a headless runner because the test window
            # itself is not presented.
            window._regression_dismissed(dialog, "review")
            self.assertEqual(window.stack.get_visible_child_name(), "readiness")
            self.assertIsNone(window.regression_dialog)
            dialog.force_close()
            pump(0.1)


if __name__ == "__main__":
    unittest.main()
