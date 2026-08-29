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
- keep embedded CLI arguments in RDP files disabled;
- keep FUSE clipboard file transfer disabled; and
- install the executable as
  `/usr/libexec/eitaas-freerdp/bin/sdl-freerdp` with private libraries and an
  `$ORIGIN`-relative runtime search path.

The prototype is not release-ready until it passes the hardware gates in
issue #27. In particular, a successful build does not prove that WebKitGTK can
select a CAC certificate during Microsoft sign-in.

The Fedora 44 hardware test confirmed two additional limitations:

- native SDL3 Wayland crashes when its libdecor GTK event processing overlaps
  WebKitGTK; EITaaS therefore forces this isolated client through XWayland; and
- the upstream WebView wrapper does not handle WebKitGTK client-certificate or
  certificate-PIN authentication requests, so CAC login is not yet available.

Do not fetch an unpinned WebView branch during a release build. Supply the
pinned WebView source as `external/webview`, which FreeRDP's build detects
without network access.
