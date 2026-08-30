"""Small reusable Libadwaita widgets for the helper window."""

from __future__ import annotations

import gettext
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from eitaas.api import StoredProfileSummary
from . import viewmodel

_ = gettext.gettext


def accessible(widget: Gtk.Widget, label: str, description: str | None = None) -> Gtk.Widget:
    """Attach an AT-SPI label (and optional description) to any widget."""
    properties = [Gtk.AccessibleProperty.LABEL]
    values: list[object] = [label]
    if description:
        properties.append(Gtk.AccessibleProperty.DESCRIPTION)
        values.append(description)
    widget.update_property(properties, values)
    return widget


class StatusRowWidget(Adw.ActionRow):
    """One readiness row: state icon, what it proves, and a copyable hint."""

    def __init__(self, row: viewmodel.StatusRow, on_copy: Callable[[str], None]) -> None:
        super().__init__(title=row.title)
        self.row = row
        state = viewmodel.state_label(row.state)
        icon = Gtk.Image.new_from_icon_name(viewmodel.state_icon(row.state))
        icon.add_css_class(_STATE_CLASSES.get(row.state, "dim-label"))
        accessible(icon, state)
        self.add_prefix(icon)
        subtitle = f"{state}. {row.detail}"
        if row.hint:
            subtitle = f"{subtitle}\n{row.hint}"
        if row.command:
            subtitle = f"{subtitle}\n{row.command}"
        self.set_subtitle(subtitle)
        self.set_subtitle_selectable(True)
        accessible(self, f"{row.title}: {state}", row.detail)
        if row.command:
            button = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
            button.set_valign(Gtk.Align.CENTER)
            button.add_css_class("flat")
            button.set_tooltip_text(_("Copy command"))
            accessible(button, _("Copy command"), row.command)
            button.connect("clicked", lambda _button: on_copy(row.command or ""))
            self.add_suffix(button)
            self.set_activatable_widget(button)


_STATE_CLASSES = {
    viewmodel.OK: "success",
    viewmodel.WARN: "warning",
    viewmodel.FAIL: "error",
}


class ProfileRowWidget(Adw.ActionRow):
    """An imported profile with a default selector and a Remove action."""

    def __init__(
        self,
        profile: StoredProfileSummary,
        group: Gtk.CheckButton | None,
        on_select: Callable[[str], None],
        on_remove: Callable[[str], None],
    ) -> None:
        super().__init__(title=profile.name, subtitle=viewmodel.profile_subtitle(profile))
        self.profile = profile
        self.check = Gtk.CheckButton()
        self.check.set_valign(Gtk.Align.CENTER)
        if group is not None:
            self.check.set_group(group)
        self.check.set_active(profile.default)
        accessible(self.check, _("Use {name} for Connect").format(name=profile.name))
        self.check.connect(
            "toggled",
            lambda button: on_select(profile.name) if button.get_active() and not profile.default else None,
        )
        self.add_prefix(self.check)
        self.set_activatable_widget(self.check)
        remove = Gtk.Button.new_with_label(_("Remove"))
        remove.set_valign(Gtk.Align.CENTER)
        remove.add_css_class("destructive-action")
        accessible(remove, _("Remove {name}").format(name=profile.name),
                   _("Deletes the imported file from your private profile store."))
        remove.connect("clicked", lambda _button: on_remove(profile.name))
        self.add_suffix(remove)
