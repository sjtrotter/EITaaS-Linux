# Isolated FreeRDP WebView prototype

This directory describes the separately packaged FreeRDP client required when
Microsoft Identity Broker is unavailable. It must install below
`/usr/libexec/eitaas-freerdp`; it must not replace distribution FreeRDP files.

The prototype is pinned to:

- FreeRDP 3.31.0, commit `aa8650b300aa4cabd85d9c72b431301509b9043f`
- `akallabeth/webview`, commit `2a0a1303c5e8c9c5b73fa9e461739042ebdabe6f`

Pinned source archive SHA-256 digests:

- FreeRDP: `3c66cdd4506b86c451dd0817cb60aa8434c32f56ac1f92aa543f332b376113af`
- WebView: `717fa4d57ab61b72dc815c5f65fa94de3fdc4218bfc2872cecb0ce8c5caf097e`

Required security properties:

- build the SDL3 client with AAD, PC/SC, SSO-MIB, and WebView enabled;
- use Fedora's supported `webkit2gtk-4.1` library;
- apply `0001-redact-webview-callback-errors.patch` before building;
- apply `0002-add-pkcs11-webview-authentication.patch` to handle
  certificate selection and PIN challenges with PKCS #11-backed credentials;
- apply `0003-honor-disabled-display-options.patch` so command-line
  single-monitor overrides can disable profile-provided display settings;
- keep embedded CLI arguments in RDP files disabled;
- keep FUSE clipboard file transfer disabled; and
- install the executable as
  `/usr/libexec/eitaas-freerdp/bin/sdl-freerdp` with private libraries and an
  `$ORIGIN`-relative runtime search path.

The Fedora prototype passed the authentication hardware gates in issue #27 on
August 29, 2026: embedded Azure Government sign-in completed with PIV
certificate selection and PIN entry, the AVD desktop loaded, and CAC
redirection was usable inside Windows. No callback URL, code, token, profile
endpoint, or PIN was emitted by EITaaS-Linux.

The Fedora 44 hardware test confirmed two additional limitations:

- native SDL3 Wayland crashes when its libdecor GTK event processing overlaps
  WebKitGTK; EITaaS therefore forces this isolated client through XWayland; and
- the upstream WebView wrapper does not handle WebKitGTK client-certificate or
  certificate-PIN authentication requests; the hardware-validated prototype
  supplies those handlers downstream.

The successful test used Fedora 44 in a GNOME Wayland session with the SDL
client forced through XWayland. A two-monitor profile had severe scaling and
pointer-target alignment problems after connection, and the fullscreen toggle
did not work. Multimonitor behavior is therefore not validated. EITaaS offers
an explicit resizable single-monitor fallback while issue #29 tracks hardware
validation and further display polish. Ubuntu, Arch
Linux, native Wayland, other desktop environments, CAC removal/reinsertion,
and disconnect/reconnect still require their own manual release-matrix tests.

FreeRDP requests more than one AAD token during connection setup. Each request
currently creates a short-lived upstream WebView window, so non-interactive
cookie-backed stages can briefly appear and close before the interactive login
window. Removing that flicker requires an upstream WebView lifetime change and
is tracked as polish rather than being mixed into the credential-handling fix.

The authentication handler calls `/usr/bin/p11tool` directly, never through a
shell. It prefers a card's enumerable private-key object matched by PKCS #11
ID. For PIN-protected keys that are not enumerable before authentication, it
uses an ID-only private-key selector without copying the certificate label.
The chooser is limited to authentication, identity, and PIV labels.
Certificate and key URIs remain in
process memory; only human-readable certificate labels appear in the chooser.
PIN input is masked, is submitted with no credential persistence, and is
cleared from the GTK entry. Core dumps are disabled before the authentication
surface is constructed. Diagnostic messages contain only challenge type,
retry state, and credential-submission state; they omit host and card metadata.

Do not fetch an unpinned WebView branch during a release build. Supply the
pinned WebView source as `external/webview`, which FreeRDP's build detects
without network access.
