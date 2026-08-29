# Shared frontend experience specification

This specification governs both the GTK and Qt applications. The goal is a
familiar remote-workspace experience, not a visual clone of Windows App.
EITaaS-Linux must always be visibly identified as independent community
software.

## Product identity

Use the name **EITaaS-Linux** and the subtitle **Community AVD connection
helper** in onboarding and About surfaces. The About view must link to `NOTICE`
and state that the application is not an official Microsoft or United States
Government client.

The project icon should combine an abstract remote display and a generic card
chip. It must not use Microsoft/Windows marks, military seals, government
agency emblems, CAC artwork, or modified copies of existing product icons.

Prefer native system typography, controls, spacing, colors, and window chrome.
The shared tokens in `design-tokens.json` describe semantic intent and minimum
dimensions; each toolkit maps them to its native theme.

## Information architecture

The primary navigation contains three destinations:

1. **Desktops** — protected profiles and connection actions.
2. **System Check** — FreeRDP, session, smart-card, and trust readiness.
3. **Settings** — connection defaults, privacy, appearance, and About.

On narrow windows these become a single content view with back navigation. On
wide windows they may use a sidebar. Certificate inspection lives under System
Check; trust modification must not be placed in the ordinary connection flow.

## Desktop resource cards

A resource card is inspired by the broadly familiar remote-desktop pattern:
thumbnail/icon, user-chosen display label, status, and primary Connect action.
It must not reproduce Windows App card art or exact styling.

A card may show:

- Profile display name (basename or user-defined alias only).
- Last-used time, stored locally only after opt-in.
- Readiness: Ready, Needs attention, or Checking.
- Backend selection when overridden from Automatic.

A card must never show a username, tenant, host-pool identifier, routing token,
full local path, authentication URL, or raw profile string value.

## First run

The first-run view explains three facts before offering an action:

- The software is an independent community client helper.
- A profile must be manually exported from the authorized AVD web client.
- The tool will validate but not upload or modify the selected profile.

Primary action: **Choose desktop profile**. Secondary action: **Run system
check**. Do not request elevated privileges during onboarding.

## Profile import

Use the desktop file chooser or portal. Accept `.rdp` and `.rdpw`; all other
extensions are rejected by the core. The application then shows a sanitized
summary containing the filename, size, permissions, and safe integer settings.

If permissions are too broad, show:

> This profile can be read by other local accounts. Restrict it to your account
> before connecting.

Offer **Fix permissions** only after the shared core gains a narrowly scoped,
tested operation. Until then, display the exact `chmod 600` recovery command
without running it automatically.

Profiles are not copied into application storage by default. **Remember this
profile** is an explicit opt-in and must explain the storage location and
removal action.

## Readiness and system check

Show four high-level groups in a stable order:

1. Remote desktop client.
2. Desktop session and display backend.
3. Smart-card service, reader, and middleware.
4. Certificate information.

Each row uses an icon plus text; never communicate state through color alone.
States are Checking, Ready, Needs attention, Unavailable, and Not checked.
Failures include one safe explanation and one recovery action. Do not offer a
generic Ignore or Connect anyway action for certificate failures.

## Connection options

The default connection sheet exposes only:

- **Smart-card passthrough** — on and required for the principal use case.
- **Clipboard sharing** — off by default, with a local/remote data warning.
- **Display backend** — Automatic by default; X11, SDL, and Wayland are under
  Advanced.

No option may disable server-certificate verification. Experimental backends
must be labeled and must not silently replace Automatic after failure.

## Connection lifecycle

Connection states are Validating, Selecting client, Starting, Authenticating,
Connected, Disconnecting, Cancelled, and Failed. Only states that the core can
verify should be shown; elapsed time does not prove Connected.

The progress view displays a concise phase and Cancel. Closing the application
while FreeRDP is active prompts **Disconnect and quit** or **Keep working**. The
frontend sets the core cancellation event and waits for cleanup.

Authentication remains owned by FreeRDP until a separately reviewed browser
handoff exists. The frontend must not scrape browser developer tools, embed a
web view, collect callback URLs, or mirror child output into a GUI log.

## Failures and recovery

An error view contains:

- Human title derived from a stable application error code.
- Redacted explanation.
- At most two concrete recovery actions.
- **Copy safe details**, which exports only the typed public result.

It must never contain raw subprocess arguments or output. Support export starts
with a preview and explicit save action; it is never uploaded automatically.

## Certificate experience

The initial certificate UI is inspection-only. It displays bundle filename,
SHA-256, certificate subjects/issuers, fingerprints, and self-signed
candidates. It must state that inspection does not establish trust.

Future trust installation requires a separate review screen showing scope,
objects to add, objects to leave untrusted, privilege requirement, and rollback
plan. There is no one-click Trust all action.

## Accessibility requirements

- Every control is reachable and operable by keyboard.
- Focus order follows visual order and returns predictably after dialogs.
- All icons have accessible names or are marked decorative.
- Status uses icon, text, and accessible state—not color alone.
- Text and essential graphics meet WCAG 2.2 AA contrast.
- Layout remains usable at 200 percent text scaling and a 360 CSS-pixel
  equivalent minimum width.
- Respect reduced-motion and high-contrast preferences.
- Progress indicators expose a textual phase; indeterminate animation is not
  the only feedback.
- Dynamic status changes use polite announcements and do not repeatedly steal
  focus.

GTK uses AT-SPI semantics provided by GTK/Libadwaita. Qt uses accessible names,
descriptions, roles, and state through Qt Accessibility. Toolkit-native
differences are expected as long as task order and meaning remain equivalent.

## Privacy and local state

Store preferences under the appropriate XDG config location and non-secret
history under XDG state. Temporary working files belong in XDG runtime with
mode `0600`. Never place profiles, profile values, child output, or callbacks in
recent-file databases, notifications, telemetry, crash reports, or analytics.

The application has no telemetry by default. If telemetry is ever proposed, it
requires a separate threat/privacy review and explicit opt-in.
