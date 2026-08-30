"""Toolkit-free presentation logic for the helper GUI.

Everything here turns typed ``eitaas.api`` results into plain-language rows
and states. Hints name the package, command, or action a person should take;
nothing in this module runs a command or touches the file system.
"""

from __future__ import annotations

import gettext
from dataclasses import dataclass
from enum import Enum

from eitaas.api import (
    ApplicationError,
    DoctorReport,
    SmartcardComponent,
    StoredProfileSummary,
)

_ = gettext.gettext

OK = "ok"
WARN = "warn"
FAIL = "fail"
UNKNOWN = "unknown"

PCSCD_COMMAND = "systemctl enable --now pcscd.socket"
CLIENT_PACKAGE = "eitaas-remmina"
TOOL_PACKAGES = {
    "pcsc_scan": "pcsc-tools",
    "pkcs11-tool": "opensc",
    "systemctl": "systemd",
    "openssl": "openssl",
    "certutil": "nss-tools (Fedora) / libnss3-tools (Debian)",
}
# The only two public AVD web clients; the helper never opens other URLs.
WEB_CLIENTS = {
    "azure_government": "https://rdweb.wvd.azure.us/arm/webclient",
    "azure_commercial": "https://client.wvd.microsoft.com/arm/webclient",
}
DEFAULT_WEB_CLIENT = "azure_government"
EXPORT_STEPS = (
    _("Open the Azure Virtual Desktop web client (button on the right)."),
    _("Sign in with your organization account in the browser. The browser may ask for your "
      "smart card (PIV) certificate and PIN."),
    _("Click the settings cog in the top right corner."),
    _("Choose \u201cDownload the rdp file\u201d."),
    _("Click your desktop (for example \u201cDesktop\u201d). A file named like Desktop.rdpw "
      "is saved to your Downloads folder."),
    _("Come back here, press \u201cI downloaded the RDP file\u201d, and pick that file."),
)
WHY_PROFILE = _(
    "The .rdpw file is a signed description of your workspace that the remote desktop client "
    "uses to reach the Azure Virtual Desktop gateway. It contains no password, but treat it as "
    "personal: EITaaS Connect moves it out of Downloads into a private folder so it is not left "
    "readable by other users of this computer."
)
CLOUD_LABELS = {
    "azure_government": _("Azure US Government"),
    "azure_commercial": _("Azure commercial"),
}


@dataclass(frozen=True)
class StatusRow:
    """One readiness line: what was checked, what it proves, what to do."""

    key: str
    title: str
    state: str
    detail: str
    hint: str | None = None
    command: str | None = None


class ConnectState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"


def state_icon(state: str) -> str:
    return {
        OK: "object-select-symbolic",
        WARN: "dialog-warning-symbolic",
        FAIL: "dialog-error-symbolic",
    }.get(state, "dialog-question-symbolic")


def state_label(state: str) -> str:
    return {
        OK: _("Ready"),
        WARN: _("Needs attention"),
        FAIL: _("Not ready"),
    }.get(state, _("Not checked"))


def _component(report: DoctorReport, name: str) -> SmartcardComponent | None:
    if report.smartcard is None:
        return None
    for item in report.smartcard.components:
        if item.name == name:
            return item
    return None


def _client_row(report: DoctorReport) -> StatusRow:
    bundle = report.remmina
    versions = _("Remmina {remmina}, FreeRDP {freerdp}").format(
        remmina=bundle.remmina_version, freerdp=bundle.freerdp_version
    )
    if bundle.launcher and bundle.client:
        return StatusRow(
            "client",
            _("Bundled remote desktop client"),
            OK,
            _("The eitaas-remmina launcher and its private client are installed ({versions}).").format(
                versions=versions
            ),
        )
    if bundle.launcher:
        detail = _("The eitaas-remmina launcher is present but its private client binary is missing.")
    else:
        detail = _("The eitaas-remmina launcher is not installed.")
    return StatusRow(
        "client",
        _("Bundled remote desktop client"),
        FAIL,
        detail,
        _("Install the {package} package for your distribution.").format(package=CLIENT_PACKAGE),
    )


def _pcscd_row(report: DoctorReport) -> StatusRow:
    component = _component(report, "pcscd")
    if report.pcsc_socket or (component and component.ok):
        return StatusRow(
            "pcscd",
            _("Smart-card service"),
            OK,
            _("The PC/SC daemon socket is available (pcscd.socket)."),
        )
    if component and not component.available:
        return StatusRow(
            "pcscd",
            _("Smart-card service"),
            UNKNOWN,
            _("systemctl is not available, so the pcscd service state could not be checked."),
            _("Install pcscd and start its socket."),
        )
    return StatusRow(
        "pcscd",
        _("Smart-card service"),
        FAIL,
        _("The pcscd socket is not active, so the reader cannot be used."),
        _("Start the service (needs administrator rights) with:"),
        PCSCD_COMMAND,
    )


def _reader_row(report: DoctorReport) -> StatusRow:
    component = _component(report, "reader")
    if component is None or not component.available:
        return StatusRow(
            "reader",
            _("Smart-card reader"),
            UNKNOWN,
            _("pcsc_scan is not installed, so no reader check could run."),
            _("Install the {package} package.").format(package=TOOL_PACKAGES["pcsc_scan"]),
        )
    if component.ok:
        return StatusRow(
            "reader",
            _("Smart-card reader"),
            OK,
            _("A reader was enumerated (pcsc_scan -r). This does not prove a card is inserted."),
        )
    return StatusRow(
        "reader",
        _("Smart-card reader"),
        FAIL,
        _("No reader was enumerated ({summary}).").format(summary=component.summary),
        _("Plug in the reader, then re-check. If it stays missing, start the smart-card service."),
    )


def _middleware_row(report: DoctorReport) -> StatusRow:
    component = _component(report, "middleware")
    if component is None or not component.available:
        return StatusRow(
            "middleware",
            _("Card middleware (OpenSC)"),
            UNKNOWN,
            _("pkcs11-tool is not installed, so the middleware check could not run."),
            _("Install the {package} package.").format(package=TOOL_PACKAGES["pkcs11-tool"]),
        )
    if component.ok:
        return StatusRow(
            "middleware",
            _("Card middleware (OpenSC)"),
            OK,
            _("OpenSC can list card slots (pkcs11-tool --list-slots). Insert your card before "
              "connecting; the client prompts for the PIN."),
        )
    return StatusRow(
        "middleware",
        _("Card middleware (OpenSC)"),
        FAIL,
        _("OpenSC could not list card slots ({summary}).").format(summary=component.summary),
        _("Check that the reader is connected and the smart-card service is running."),
    )


def _session_row(report: DoctorReport) -> StatusRow:
    if report.display or report.wayland_display:
        return StatusRow(
            "session",
            _("Desktop session"),
            OK,
            _("A graphical session is available ({kind}).").format(kind=report.session_type),
        )
    return StatusRow(
        "session",
        _("Desktop session"),
        FAIL,
        _("No display was detected, so the remote desktop window cannot open."),
        _("Run EITaaS Connect from a graphical desktop session."),
    )


def _tools_row(report: DoctorReport) -> StatusRow:
    missing = sorted(name for name, present in report.tools.items() if not present)
    if not missing:
        return StatusRow(
            "tools",
            _("Diagnostic tools"),
            OK,
            _("All optional diagnostic tools are installed."),
        )
    packages = ", ".join(TOOL_PACKAGES.get(name, name) for name in missing)
    return StatusRow(
        "tools",
        _("Diagnostic tools"),
        WARN,
        _("Missing: {tools}. They are optional for connecting.").format(tools=", ".join(missing)),
        _("Install: {packages}").format(packages=packages),
    )


def readiness_rows(report: DoctorReport | None, error: ApplicationError | None = None) -> list[StatusRow]:
    """Plain-language rows in a stable order; an error yields one UNKNOWN row."""
    if report is None:
        detail = error.message if error else _("The readiness check has not run yet.")
        return [StatusRow("doctor", _("Readiness check"), UNKNOWN, detail, _("Press Re-check."))]
    return [
        _client_row(report),
        _session_row(report),
        _pcscd_row(report),
        _reader_row(report),
        _middleware_row(report),
        _tools_row(report),
    ]


def can_connect(report: DoctorReport | None, profile: StoredProfileSummary | None) -> bool:
    """Connect is enabled when the launcher exists and a default profile is stored."""
    return bool(report and report.remmina.launcher and profile is not None)


def readiness_summary(report: DoctorReport | None, rows: list[StatusRow]) -> str:
    if report is None:
        return _("Readiness has not been checked.")
    failures = [row.title for row in rows if row.state == FAIL]
    if not failures:
        return _("All required checks passed.")
    return _("Needs attention: {items}.").format(items=", ".join(failures))


def cloud_label(cloud: str) -> str:
    return CLOUD_LABELS.get(cloud, cloud)


def web_client_url(cloud: str) -> str:
    """Only the two public web clients can be opened; anything else is refused."""
    return WEB_CLIENTS[cloud]


def profile_subtitle(profile: StoredProfileSummary) -> str:
    return _("{cloud} · {size} bytes · mode {mode} · imported {date}").format(
        cloud=cloud_label(profile.cloud),
        size=profile.size,
        mode=profile.mode,
        date=profile.imported.replace("T", " "),
    )


def connect_description(profile: StoredProfileSummary | None, summary: str) -> str:
    if profile is None:
        return _("Import a profile on the Profile page first. {summary}").format(summary=summary)
    return _("Connect opens {name} in the bundled remote desktop client. Sign-in, certificate "
             "selection, and the PIN prompt happen in that window. {summary}").format(
        name=profile.name, summary=summary
    )


ERROR_TITLES = {
    "launch_failed": _("Could not start the connection"),
    "profile_import_failed": _("Could not import the profile"),
    "profile_store_failed": _("Could not update the profile list"),
    "doctor_failed": _("Could not run the readiness check"),
}


def error_text(error: ApplicationError) -> tuple[str, str]:
    """A stable human title plus the redacted message and recovery hint."""
    title = ERROR_TITLES.get(error.code, _("Something went wrong"))
    body = error.message
    if error.recovery:
        body = f"{body}\n\n{error.recovery}"
    return title, body


def exit_text(exit_code: int, cancelled: bool) -> str | None:
    """Text after the client exits; None means nothing needs to be shown."""
    if cancelled:
        return _("Connection cancelled.")
    if exit_code == 0:
        return None
    return _("The remote desktop client exited with status {code}.").format(code=exit_code)


def diagnostic_text(exit_code: int, reason_lines: tuple[str, ...], log_path: str | None) -> str:
    """In-place text for a failed run: status, the last reason-code lines, and where the log is.

    The lines come from the redacted session log and carry only stable reason
    codes, counts, and Remmina warnings; the full log is offered through a copy
    button rather than shown.
    """
    parts = [exit_text(exit_code, False)
             or _("The remote desktop client exited normally but reported smart-card warnings.")]
    if reason_lines:
        parts.append(_("Last diagnostic lines:"))
        parts.extend(reason_lines)
    else:
        parts.append(_("The client reported no smart-card diagnostic lines."))
    if log_path:
        parts.append(_("Diagnostic log: {path}").format(path=log_path))
    return "\n".join(part for part in parts if part)
