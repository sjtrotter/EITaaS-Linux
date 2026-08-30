# EITaaS Connect experience specification

This specification describes the GTK 4/Libadwaita helper `eitaas-gui`
(application id `org.eitaas.Helper`), the graphical frontend of EITaaS-Linux.
It states what the shipped code does; controls that are not implemented are
not described. The helper is not a connection manager (ADR-0002): it checks
readiness, imports one exported profile at a time, and starts the bundled
one-shot `eitaas-remmina` client.

## Product identity

The window title and product name are **EITaaS Connect**; the subtitle in
`design-tokens.json` is **Community AVD connection helper**. The desktop entry
(`data/org.eitaas.Helper.desktop`) uses the generic name "Remote desktop setup
helper". Documentation and `NOTICE` state that the software is independent
community work, not an official Microsoft or United States Government client.

The project icon (`org.eitaas.Helper`) combines an abstract remote display and
a generic card chip. It must not use Microsoft/Windows marks, military seals,
government agency emblems, smart card (PIV) artwork, or modified copies of
existing product icons.

The helper uses native Libadwaita controls, typography, spacing, and window
chrome, and follows the system light/dark preference. `design-tokens.json`
records semantic intent and minimum dimensions only.

## Information architecture

An `Adw.ViewStack` holds three pages, switched from the header bar on wide
windows and from a bottom switcher bar below 550 sp:

1. **Readiness** — `eitaas doctor` rendered as plain-language rows with a
   Re-check button.
2. **Profile** — export steps, the import button, the import banner, and the
   list of imported profiles.
3. **Connect** — a status page with the Connect button, the running state,
   and any launch error.

### Startup page selection

On first run — no recorded readiness pass, or no default profile — the window
opens on Readiness and the flow stays Readiness → Profile → Connect. When a
previous run recorded a readiness pass (see the marker under "Privacy and
local state") and a default profile exists, the window opens directly on
Connect. Either way the doctor check runs on every start, in the background,
with no blocking splash; a pass rewrites the marker. If a check that passed
last time now hard-fails (a regression), the marker is cleared and — when the
Readiness page is not already visible — an alert dialog names the failing
checks; dismissing it in any way (button, Escape, or close) switches to the
Readiness page. The dialog uses a normal `Adw.AlertDialog` with an async
response handler; it never blocks the main loop.

## Profile import

The Profile page shows a **Web client** chooser (Azure US Government by
default, or Azure commercial; these two public web-client URLs are the only
ones the helper opens, via `Gtk.UriLauncher`) and six numbered steps as list
rows: open the web client (button on step 1), sign in with the organization
account (the browser may ask for the smart card (PIV) certificate and PIN),
click the settings cog, choose "Download the rdp file", click the desktop
(saves e.g. `Desktop.rdpw` to Downloads), then press **I downloaded the RDP
file**, which opens `Gtk.FileDialog` filtered to `*.rdpw`, starting in the
Downloads directory. A "Why do I need this file?" expander explains that the
`.rdpw` is a signed, password-free description of the workspace, is personal,
and is moved out of Downloads so other users cannot read it.

Import calls `Application.import_profile`, which *moves* the chosen file
(rename, or copy + fsync + unlink across filesystems; symlinks and files owned
by another user are refused) into `$XDG_DATA_HOME/eitaas-remmina/profiles/`
(directory mode `0700`, file mode `0600`), keeps the basename (adding `-2`,
`-3`, … on collision), re-validates it, and makes it the default. The step text
explains that the file is moved out of Downloads so it is not left readable by
other accounts. A toast confirms "Imported NAME; it is now the default."

The **Imported profiles** list shows one row per stored file: basename, cloud
label, size, mode, and import date (exactly the `StoredProfileSummary` fields).
A radio button labelled "Use NAME for Connect" selects the default; **Remove**
opens a confirmation dialog (Keep / Remove) and then deletes the stored file.
The helper never reads profile contents beyond what `inspect_profile` returns
and never shows a full path.

`eitaas-gui FILE.rdpw`, the desktop entry's `%f`, and double-clicking a file of
MIME type `application/x-eitaas-rdpw` open the Profile page with the banner
"Import FILE into your private profile store?" and an **Import** button. There
is no automatic import and no automatic connect; the person presses Import,
then Connect.

## Readiness

Rows appear in a stable order: bundled remote desktop client, desktop session,
smart-card service, smart-card reader, card middleware (OpenSC), diagnostic
tools. Each row is an `Adw.ActionRow` with a state icon, the
state word, one sentence saying what was checked and what it proves, and,
where applicable, a hint naming the package to install or the command to run.
A command (for example `systemctl enable --now pcscd.socket`) is shown as text
with a Copy button; the helper never runs it.

States map to `DoctorReport` values: **Ready** (`ok`), **Needs attention**
(`warn`), **Not ready** (`fail`), and **Not checked** (`unknown`, used before
the first run, when a tool is missing, or when `doctor` itself fails). State is
conveyed by icon, text, and the accessible label together, never by colour
alone. **Re-check** reruns `doctor_async` and is disabled while it runs.

## Connection lifecycle

Connect is disabled only on hard failures: the readiness report must show the
`eitaas-remmina` launcher and its private client binary, and a default profile
must exist. Warnings — missing diagnostic tools, or a smart-card check failure
the client can surface itself — never disable the button. Pressing it runs `Application.launch`
with `ConnectionRequest()` (the stored default) on a worker thread. The button
is replaced by a spinner, a phase label, and **Cancel**; the phase label shows
"Starting" and then the `launch` progress messages for the `validating`,
`starting`, and `cancelling` phases. Cancel sets the cancellation event and
shows "Stopping the remote desktop client".

The core cannot observe authentication or session establishment, so there is
no Authenticating or Connected state. Sign-in, certificate selection, and the
PIN prompt happen in the Remmina window. A cancelled run reports
"Connection cancelled." as a toast and a clean run with no warnings shows
nothing. Import and profile rows are disabled while a connection is running.

Closing the window while the client runs asks **Disconnect and quit** /
**Keep working** (default Keep working). Quit sets the cancellation event and
joins the worker with a 7 s grace period.

## Diagnostics after a failed run

A run that exits non-zero, or that exits cleanly but logged `smartcard-auth:`
warning lines, shows `viewmodel.diagnostic_text` in place on the Connect page:
the exit status (or "exited normally but reported smart-card warnings"), the
last reason-code and Remmina warning lines from the redacted session log, and
the log's path. The lines are fetched with `Application.session_log` on a
worker thread, so the page first shows the status and path and then gains the
lines. A **Copy diagnostic log** button appears with them and places the whole
redacted log on the clipboard. Raw child output never reaches the page by any
other route.

## Failures and recovery

A failed launch is shown in place on the Connect page as a selectable card
containing a human title derived from the error code (`launch_failed`,
`profile_import_failed`, `profile_store_failed`, `doctor_failed`, otherwise
"Something went wrong"), the redacted message, and the recovery text when the
core supplies one. Import and profile-store failures use an alert dialog with
the same title and body. Child output, launcher arguments, and full paths never
appear.

## Deliberate decisions

The smart-card PIN dialog lives in the bundled Remmina client, not in this
helper. Its PIN entry submits only through the explicit confirmation button;
pressing Enter does not confirm the dialog. This is the owner's deliberate
choice (issue #85) to avoid accidental submission of a partially typed PIN —
each wrong attempt counts against the card's retry limit — and it is
explicitly out of scope to add Enter-to-confirm behaviour.

## Accessibility requirements

- Every control is reachable and operable by keyboard. Accelerators: Ctrl+R
  re-check, Ctrl+O import, Ctrl+Return connect, Ctrl+Q quit.
- Focus order follows visual order and returns predictably after dialogs.
- Every control and state icon carries an AT-SPI label (`widgets.accessible`);
  the copy button's description is the command it copies.
- Status uses icon, text, and accessible state, not colour alone.
- Text and essential graphics meet WCAG 2.2 AA contrast through the system
  theme.
- The window has a 360 × 400 minimum size and remains usable at 200 percent
  text scaling; the page switcher moves to the bottom bar on narrow windows.
- Progress exposes a textual phase; the spinner is not the only feedback.
- Results arrive through toasts and row updates; nothing steals focus while a
  check is running.

## Privacy and local state

- `$XDG_DATA_HOME/eitaas-remmina/profiles/` holds the imported `.rdpw` files
  (directory `0700`, files `0600`).
- `$XDG_CONFIG_HOME/eitaas/profiles.ini` holds only `[profiles] default = NAME`
  (mode `0600`).
- `$XDG_STATE_HOME/eitaas-gui/last-readiness-pass.json` (directory `0700`,
  file `0600`) records the last readiness pass: an ISO-8601 timestamp and a
  SHA-256 hash of the readiness row states — never profile data, paths, or
  check output. It decides the startup page, is rewritten on every pass, and
  is cleared on a regression. The hash is recorded for inspection only;
  regressions are detected from the fresh check results, never by comparing
  hashes. Unknown states (a missing diagnostic tool) count as a pass, like
  warnings.
- User-visible strings are wrapped in gettext; no translations ship yet.
- No other state, history, or recent-file entry is written. Profiles, profile
  values, child output, and callbacks never reach notifications, logs, or
  crash reports. There is no telemetry.
