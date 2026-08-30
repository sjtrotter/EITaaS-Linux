"""EITaaS Connect: a GTK 4 / Libadwaita setup-and-connect helper.

Every ``eitaas.api.Application`` call runs on a worker thread; results are
marshalled back with ``GLib.idle_add``. The window never reads profile
contents, never builds client arguments, and never runs privileged commands.
"""

from __future__ import annotations

import gettext
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from eitaas.api import (  # noqa: E402
    Application,
    ApplicationError,
    ConnectionRequest,
    DoctorReport,
    ProgressEvent,
    Result,
    StoredProfileSummary,
)
from . import viewmodel  # noqa: E402
from .viewmodel import ConnectState  # noqa: E402
from .widgets import ProfileRowWidget, StatusRowWidget, accessible  # noqa: E402

_ = gettext.gettext
APP_ID = "org.eitaas.Helper"
EXPORT_HELP_URL = "https://github.com/sjtrotter/EITaaS-Linux#current-workflow"


def _on_main(callback: Callable[..., object], *args: object) -> None:
    """Run ``callback`` on the GTK main loop exactly once."""
    GLib.idle_add(lambda: (callback(*args), GLib.SOURCE_REMOVE)[1])


class HelperWindow(Adw.ApplicationWindow):
    """Three pages: Readiness, Profile, Connect."""

    def __init__(self, core: Application, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.core = core
        self.report: DoctorReport | None = None
        self.rows: list[viewmodel.StatusRow] = []
        self.profiles: tuple[StoredProfileSummary, ...] = ()
        self.pending_import: Path | None = None
        self.connect_state = ConnectState.IDLE
        self.cancel_event: threading.Event | None = None
        self.worker: threading.Thread | None = None
        self.quit_pending = False
        self.set_title(_("EITaaS Connect"))
        self.set_default_size(680, 600)
        self.set_size_request(360, 400)
        self._build()
        self.connect("close-request", self._on_close_request)
        self.refresh_readiness()
        self.refresh_profiles()

    # ----- layout -------------------------------------------------------

    def _build(self) -> None:
        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        view = Adw.ToolbarView()
        self.toasts.set_child(view)
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header = Adw.HeaderBar(title_widget=switcher)
        view.add_top_bar(header)
        view.set_content(self.stack)
        bar = Adw.ViewSwitcherBar(stack=self.stack)
        view.add_bottom_bar(bar)
        # Narrow windows move the page switcher to the bottom bar.
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 550sp"))
        narrow.add_setter(bar, "reveal", True)
        # PyGObject cannot express a NULL GValue setter, so swap the title via signals.
        narrow.connect("apply", lambda _bp: header.set_title_widget(None))
        narrow.connect("unapply", lambda _bp: header.set_title_widget(switcher))
        self.add_breakpoint(narrow)
        self.stack.add_titled_with_icon(
            self._build_readiness(), "readiness", _("Readiness"), "object-select-symbolic"
        )
        self.stack.add_titled_with_icon(
            self._build_profile(), "profile", _("Profile"), "document-open-symbolic"
        )
        self.stack.add_titled_with_icon(
            self._build_connect(), "connect", _("Connect"), "network-server-symbolic"
        )

    def _build_readiness(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        self.readiness_group = Adw.PreferencesGroup(
            title=_("System readiness"),
            description=_("Each line states what was checked and what to do if it failed. "
                          "Nothing is changed on your system; commands are shown for you to run."),
        )
        self.recheck = Gtk.Button.new_with_label(_("Re-check"))
        self.recheck.add_css_class("flat")
        accessible(self.recheck, _("Re-check readiness"))
        self.recheck.connect("clicked", lambda _button: self.refresh_readiness())
        self.readiness_group.set_header_suffix(self.recheck)
        page.add(self.readiness_group)
        self.readiness_rows: list[Gtk.Widget] = []
        return page

    def _build_profile(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        self.import_banner = Adw.Banner(button_label=_("Import"))
        self.import_banner.connect("button-clicked", lambda _banner: self._import_pending())
        accessible(self.import_banner, _("Profile opened from the file manager"))
        page.add(self._banner_group(self.import_banner))
        steps = "\n".join(f"{index}. {text}" for index, text in enumerate(viewmodel.EXPORT_STEPS, 1))
        export = Adw.PreferencesGroup(title=_("Get your desktop profile"), description=steps)
        link = Gtk.LinkButton.new_with_label(EXPORT_HELP_URL, _("Export instructions (project documentation)"))
        link.set_halign(Gtk.Align.START)
        accessible(link, _("Open the export instructions in a browser"))
        export.add(link)
        self.import_button = Gtk.Button.new_with_label(_("I downloaded the RDP file"))
        self.import_button.add_css_class("suggested-action")
        self.import_button.add_css_class("pill")
        self.import_button.set_halign(Gtk.Align.START)
        accessible(self.import_button, _("Choose the downloaded .rdpw file to import"))
        self.import_button.connect("clicked", lambda _button: self.choose_profile())
        export.add(self.import_button)
        page.add(export)
        self.profile_group = Adw.PreferencesGroup(
            title=_("Imported profiles"),
            description=_("Stored privately under your user data directory (mode 0600). "
                          "The selected profile is what Connect opens."),
        )
        page.add(self.profile_group)
        self.profile_rows: list[Gtk.Widget] = []
        return page

    @staticmethod
    def _banner_group(banner: Adw.Banner) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.add(banner)
        return group

    def _build_connect(self) -> Gtk.Widget:
        self.status_page = Adw.StatusPage(icon_name="network-server-symbolic", title=_("Connect"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        self.connect_button = Gtk.Button.new_with_label(_("Connect"))
        self.connect_button.add_css_class("suggested-action")
        self.connect_button.add_css_class("pill")
        self.connect_button.set_sensitive(False)
        accessible(self.connect_button, _("Connect"),
                   _("Starts the bundled remote desktop client with the selected profile."))
        self.connect_button.connect("clicked", lambda _button: self.start_connection())
        box.append(self.connect_button)
        self.progress_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                                    halign=Gtk.Align.CENTER, visible=False)
        self.spinner = Gtk.Spinner()
        self.progress_box.append(self.spinner)
        self.phase_label = Gtk.Label(label="")
        accessible(self.phase_label, _("Connection phase"))
        self.progress_box.append(self.phase_label)
        self.cancel_button = Gtk.Button.new_with_label(_("Cancel"))
        accessible(self.cancel_button, _("Cancel the connection"))
        self.cancel_button.connect("clicked", lambda _button: self.cancel_connection())
        self.progress_box.append(self.cancel_button)
        box.append(self.progress_box)
        self.error_label = Gtk.Label(wrap=True, visible=False, justify=Gtk.Justification.CENTER,
                                     selectable=True, max_width_chars=60)
        self.error_label.add_css_class("card")
        self.error_label.add_css_class("error")
        accessible(self.error_label, _("Connection error"))
        box.append(self.error_label)
        self.status_page.set_child(box)
        return self.status_page

    # ----- background helpers ------------------------------------------

    def _background(self, work: Callable[[], Result], done: Callable[[Result], None]) -> None:
        """Run an API call off the main loop and deliver the result on it."""
        thread = threading.Thread(
            target=lambda: _on_main(done, work()), name="eitaas-gui-api", daemon=True
        )
        thread.start()

    def _future(self, future: Future, done: Callable[[Result], None]) -> None:
        future.add_done_callback(lambda finished: _on_main(done, finished.result()))

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=text))

    def show_error(self, error: ApplicationError) -> None:
        title, body = viewmodel.error_text(error)
        dialog = Adw.AlertDialog(heading=title, body=body)
        dialog.add_response("close", _("Close"))
        dialog.present(self)

    # ----- readiness ---------------------------------------------------

    def refresh_readiness(self) -> None:
        self.recheck.set_sensitive(False)
        self._render_rows(viewmodel.readiness_rows(None))
        self._future(self.core.doctor_async(), self._readiness_done)

    def _readiness_done(self, result: Result[DoctorReport]) -> None:
        self.report = result.value
        self._render_rows(viewmodel.readiness_rows(result.value, result.error))
        self.recheck.set_sensitive(True)
        self._update_connect()

    def _render_rows(self, rows: list[viewmodel.StatusRow]) -> None:
        for widget in self.readiness_rows:
            self.readiness_group.remove(widget)
        self.rows = rows
        self.readiness_rows = [StatusRowWidget(row, self.copy_text) for row in rows]
        for widget in self.readiness_rows:
            self.readiness_group.add(widget)

    def copy_text(self, text: str) -> None:
        self.get_clipboard().set(text)
        self.toast(_("Copied to clipboard"))

    # ----- profiles ----------------------------------------------------

    def refresh_profiles(self) -> None:
        self._future(self.core.list_profiles_async(), self._profiles_done)

    def _profiles_done(self, result: Result[tuple[StoredProfileSummary, ...]]) -> None:
        if result.error:
            self.show_error(result.error)
            return
        self.profiles = result.value or ()
        for widget in self.profile_rows:
            self.profile_group.remove(widget)
        self.profile_rows = []
        group: Gtk.CheckButton | None = None
        for profile in self.profiles:
            row = ProfileRowWidget(profile, group, self.select_profile, self.remove_profile)
            group = group or row.check
            self.profile_rows.append(row)
        if not self.profile_rows:
            self.profile_rows.append(Adw.ActionRow(title=_("No profile imported yet"),
                                                   subtitle=_("Use the button above after exporting one.")))
        for widget in self.profile_rows:
            self.profile_group.add(widget)
        self._update_connect()

    @property
    def default_profile(self) -> StoredProfileSummary | None:
        for profile in self.profiles:
            if profile.default:
                return profile
        return None

    def offer_import(self, path: Path) -> None:
        """Called for ``eitaas-gui FILE.rdpw`` / a double-clicked profile."""
        self.pending_import = path
        self.import_banner.set_title(_("Import {name} into your private profile store?").format(name=path.name))
        self.import_banner.set_revealed(True)
        self.stack.set_visible_child_name("profile")

    def _import_pending(self) -> None:
        path, self.pending_import = self.pending_import, None
        self.import_banner.set_revealed(False)
        if path is not None:
            self.import_profile(path)

    def choose_profile(self) -> None:
        dialog = Gtk.FileDialog(title=_("Choose the downloaded .rdpw profile"), modal=True)
        rdpw = Gtk.FileFilter()
        rdpw.set_name(_("Remote desktop profiles (*.rdpw)"))
        rdpw.add_pattern("*.rdpw")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(rdpw)
        dialog.set_filters(filters)
        dialog.set_default_filter(rdpw)
        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if downloads:
            dialog.set_initial_folder(Gio.File.new_for_path(downloads))
        dialog.open(self, None, self._file_chosen)

    def _file_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            chosen = dialog.open_finish(result)
        except GLib.Error:
            return
        path = chosen.get_path() if chosen else None
        if path:
            self.import_profile(Path(path))

    def import_profile(self, path: Path) -> None:
        self.import_button.set_sensitive(False)
        self._future(self.core.import_profile_async(str(path)), self._import_done)

    def _import_done(self, result: Result[StoredProfileSummary]) -> None:
        self.import_button.set_sensitive(True)
        if result.error:
            self.show_error(result.error)
            return
        self.toast(_("Imported {name}; it is now the default.").format(name=result.value.name))
        self.refresh_profiles()

    def select_profile(self, name: str) -> None:
        self._background(lambda: self.core.select_profile(name), self._store_changed)

    def remove_profile(self, name: str) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Remove {name}?").format(name=name),
            body=_("The imported file is deleted from your private profile store."),
        )
        dialog.add_response("cancel", _("Keep"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.connect("response", lambda _dialog, response: self._remove_confirmed(name, response))
        dialog.present(self)

    def _remove_confirmed(self, name: str, response: str) -> None:
        if response == "remove":
            self._background(lambda: self.core.remove_profile(name), self._store_changed)

    def _store_changed(self, result: Result) -> None:
        if result.error:
            self.show_error(result.error)
        self.refresh_profiles()

    # ----- connect -----------------------------------------------------

    def _update_connect(self) -> None:
        summary = viewmodel.readiness_summary(self.report, self.rows)
        profile = self.default_profile
        self.status_page.set_description(viewmodel.connect_description(profile, summary))
        idle = self.connect_state is ConnectState.IDLE
        self.connect_button.set_sensitive(idle and viewmodel.can_connect(self.report, profile))
        self.connect_button.set_visible(idle)
        self.progress_box.set_visible(not idle)
        self.import_button.set_sensitive(idle)
        for row in self.profile_rows:
            row.set_sensitive(idle)

    def start_connection(self) -> None:
        if self.connect_state is not ConnectState.IDLE:
            return
        if not viewmodel.can_connect(self.report, self.default_profile):
            return
        self.error_label.set_visible(False)
        self.cancel_event = threading.Event()
        self.connect_state = ConnectState.RUNNING
        self.spinner.start()
        self.phase_label.set_label(_("Starting"))
        self._update_connect()
        cancel = self.cancel_event

        def work() -> None:
            result = self.core.launch(
                ConnectionRequest(),
                on_progress=lambda event: _on_main(self._progress, event),
                cancel=cancel,
            )
            _on_main(self._launch_done, result)

        self.worker = threading.Thread(target=work, name="eitaas-gui-launch", daemon=True)
        self.worker.start()

    def _progress(self, event: ProgressEvent) -> None:
        self.phase_label.set_label(event.message)
        self.cancel_button.set_sensitive(event.cancellable or event.phase == "validating")

    def cancel_connection(self) -> None:
        if self.cancel_event is not None and self.connect_state is ConnectState.RUNNING:
            self.connect_state = ConnectState.CANCELLING
            self.phase_label.set_label(_("Stopping the remote desktop client"))
            self.cancel_button.set_sensitive(False)
            self.cancel_event.set()

    def _launch_done(self, result: Result) -> None:
        self.connect_state = ConnectState.IDLE
        self.spinner.stop()
        self.cancel_button.set_sensitive(True)
        self.worker = None
        self.cancel_event = None
        if self.quit_pending:
            self.destroy()
            return
        if result.error:
            title, body = viewmodel.error_text(result.error)
            self.error_label.set_label(f"{title}\n{body}")
            self.error_label.set_visible(True)
        else:
            text = viewmodel.exit_text(result.value.exit_code, result.value.cancelled)
            if text:
                self.toast(text)
        self._update_connect()

    # ----- shutdown ----------------------------------------------------

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        if self.connect_state is ConnectState.IDLE:
            return False
        if self.quit_pending:
            return True
        dialog = Adw.AlertDialog(
            heading=_("Disconnect and quit?"),
            body=_("The remote desktop client is still running."),
        )
        dialog.add_response("keep", _("Keep working"))
        dialog.add_response("quit", _("Disconnect and quit"))
        dialog.set_response_appearance("quit", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("keep")
        dialog.connect("response", self._quit_response)
        dialog.present(self)
        return True

    def _quit_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response == "quit":
            self.request_quit()

    def request_quit(self) -> None:
        """Quit now when idle; otherwise cancel the launch and quit once it ends.

        The worker is never joined on the GTK thread: the window hides, the
        cancellation event stops the child, and ``_launch_done`` destroys the
        window (ending the application) after the child has exited.
        """
        if self.connect_state is ConnectState.IDLE:
            self.destroy()
            return
        self.quit_pending = True
        self.set_visible(False)
        if self.cancel_event is not None:
            self.cancel_event.set()


class HelperApplication(Adw.Application):
    """``eitaas-gui [PROFILE.rdpw]``; opening a file offers to import it."""

    def __init__(self, core: Application | None = None, **kwargs: object) -> None:
        kwargs.setdefault("application_id", APP_ID)
        kwargs.setdefault("flags", Gio.ApplicationFlags.HANDLES_OPEN)
        super().__init__(**kwargs)
        self.core = core or Application()

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._action("quit", self._quit, ["<Control>q"])
        self._action("recheck", lambda: self._with_window(HelperWindow.refresh_readiness), ["<Control>r"])
        self._action("import", lambda: self._with_window(HelperWindow.choose_profile), ["<Control>o"])
        self._action("connect", lambda: self._with_window(HelperWindow.start_connection), ["<Control>Return"])

    def _action(self, name: str, callback: Callable[[], object], accelerators: list[str]) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", lambda _action, _parameter: callback())
        self.add_action(action)
        self.set_accels_for_action(f"app.{name}", accelerators)

    def _quit(self) -> None:
        window = self.props.active_window
        if isinstance(window, HelperWindow):
            window.request_quit()
        else:
            self.quit()

    def _with_window(self, method: Callable[[HelperWindow], object]) -> None:
        window = self.props.active_window
        if isinstance(window, HelperWindow):
            method(window)

    def window(self) -> HelperWindow:
        window = self.props.active_window
        if not isinstance(window, HelperWindow):
            window = HelperWindow(self.core, application=self)
        return window

    def do_activate(self) -> None:
        self.window().present()

    def do_open(self, files: list[Gio.File], _count: int, _hint: str) -> None:
        window = self.window()
        path = files[0].get_path() if files else None
        if path:
            window.offer_import(Path(path))
        if len(files) > 1:
            window.toast(_("Only the first of {count} files is offered for import.").format(count=len(files)))
        window.present()


def run(argv: list[str]) -> int:
    return HelperApplication().run(argv)
