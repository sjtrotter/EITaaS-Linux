# Isolated Remmina prototype

This directory holds the bundle inputs every packaging format consumes: the
pinned source and ordered patch data in `sources.json`, the CAC integration
sources, the `eitaas-remmina` launcher, the notices, and the Arch snapshot
date. The recipes themselves live in `packaging/rpm/eitaas-linux.spec`,
`packaging/debian/`, and `packaging/arch/PKGBUILD` -- one binary package,
`eitaas-linux`, per distribution (#80). The cross-distribution delivery
decision and validation matrix are recorded in
`docs/adr/0001-remmina-packaging-strategy.md`.

That package combines a private Remmina 1.4.43 build with private FreeRDP
3.30.0 libraries under a distribution-native private prefix
(`/usr/libexec/eitaas-remmina` on Fedora and `/usr/lib/eitaas-remmina` on
Debian-family and Arch systems) with the `eitaas` command-line helper and the
EITaaS Connect GTK 4 helper. It does not replace the distribution packages.

The downstream patches require the FreeRDP 3.16 settings API
(`FreeRDP_GatewayAvdScope` and `FreeRDP_GatewayAvdAccessAadFormat`, added in
3.16.0; the other AVD/AAD settings they use are older). The bundle pins the
FreeRDP release recorded in `sources.json`, currently the 3.30.x line that
Fedora ships, and that exact Remmina/FreeRDP pair is what the hardware gates
are run against; treat "tested with 3.30.x" as a validation statement, not a
compile-time minimum. The bundle does not link SSO-MIB: the only supported
sign-in path is the embedded WebKitGTK CAC WebView (see below).

The downstream changes preserve the original protected RDPW profile through
FreeRDP's parser, select ARM/AAD transport, honor smart-card redirection, and
handle WebKitGTK client-certificate and PIN challenges with PKCS #11-backed
CAC credentials. Only authentication, identity, and PIV-labelled certificates
are shown. Certificate discovery runs on a worker while a cancellable progress
dialog keeps the GTK interface responsive. Cancelling discovery ends the
containing AVD authentication attempt. Core dumps are disabled before opening
the authentication view.

The handler accepts certificate and PIN challenges only from the exact HTTPS
authority that initiated the AAD WebView, limited to supported Microsoft
commercial and US Government login hosts. It rejects proxy, mismatched,
standalone PIN, and insecure-origin challenges. PKCS #11 discovery uses the
`p11tool` this build pins (`-DREMMINA_P11TOOL=/usr/bin/p11tool`, the path the
package's `gnutls-utils`/`gnutls-bin` dependency installs; a build that pins
nothing searches `PATH` instead), a 15-second cancellation deadline, one
concurrent discovery, and explicit output/object limits. When that tool is
missing the dialog names the package to install instead of showing an empty
certificate list. Protected profiles are limited
to 1 MiB, opened without following symlinks, retained as one immutable buffer, and parsed
from a verified bounded buffer exactly once during pre-connect initialization.
A profile that selects the ARM resource provider without naming a gateway host
is not an Azure Virtual Desktop connection file and is refused at import; one
that does not select ARM is imported as an ordinary RDP profile. Invalid or
disallowed profile content ends the connection with an error, never by
aborting the client.

Authentication cloud selection is automatic. Protected profiles whose gateway
ends in `.wvd.azure.us` use the Azure Government authority and AVD scope;
commercial Azure profiles retain FreeRDP's normal defaults. Remmina's browser
authentication reads the scope selected in the FreeRDP settings instead of a
compiled-in commercial-cloud scope. Government profiles retain the registered
commercial `common/oauth2/nativeclient` callback used by FreeRDP's working AVD
command-line flow; the authorization authority and resource scope remain in
Azure Government.

Pinned Remmina source:

- commit `030946c83fe1b7218a21b6d32f9c975b243b7031`
- SHA-256 `8976850314dddab8cfe74f413233a712e7ba4b6ccf72b56cbf635b51f1ea2801`

Build the combined package for one distribution with:

```console
scripts/build-rpm.sh    # Fedora, RPM
scripts/build-deb.sh    # Ubuntu 24.04 or Debian 13, native DEB
scripts/build-arch.sh   # Arch Linux (must run unprivileged)
```

Each builder consumes the same `sources.json`, verifies both upstream archives
against their SHA-256 digests, applies the same ordered patch series, forces a
single compile job, and writes the binary package and its corresponding source
artifacts to `dist/`. `scripts/prepare-bundle-source.py` does the fetching and
tree assembly for all three. The Arch builder uses the repository snapshot
recorded in `SNAPSHOT`. These packages are build- and lifecycle-tested in clean
containers by `scripts/test-{deb,rpm,arch}-lifecycle.sh`; Azure Government and
CAC hardware validation is still required on each distribution before it
becomes a supported runtime target.

Release and reproducibility builds use the repository date in `SNAPSHOT`.
GitHub-hosted Azure runners cannot currently retrieve dated repositories from
either Arch archive endpoint, so CI uses Arch's current official repositories
only to validate that the package builds and passes its install, upgrade,
linkage, and removal lifecycle. A passing CI job is therefore a compatibility
check, not proof that the recorded release environment was reproduced.

After installation, launch only through:

```console
eitaas-remmina "$HOME/Downloads/Desktop.rdpw"
```

This command is a one-shot connection: cancelling CAC authentication closes
the authentication flow and the isolated Remmina application instead of
leaving its connection manager open. A no-argument connection-manager mode is
intentionally not part of the EITaaS product.

The launcher uses an isolated configuration directory below
`$XDG_STATE_HOME/eitaas-remmina` (or `~/.local/state/eitaas-remmina`) so user
plugins and settings from the distribution Remmina installation are not mixed
with the prototype.

The launcher also starts the client with `--gapplication-app-id=org.eitaas.Remmina`
(Remmina registers its GApplication with `G_APPLICATION_CAN_OVERRIDE_APP_ID`),
so the one-shot client does not share an application id with a distribution
Remmina. Without this, a Remmina already running under `org.remmina.Remmina`
(tray icon, autostart, or a leftover instance) would become the primary
instance, receive our `--connect` command line, handle it without the
smart-card patches, and our process would exit with the primary's status.

## Diagnostics

`eitaas_cac_auth.c` logs every smart-card authentication stage through
Remmina's debug and warning channels with a stable `smartcard-auth: <code>`
reason code: the WebKit challenge (scheme, host, port, proxy flag) and whether
it was accepted, discovery start and the token/certificate counts, the
label-filter outcome (kept/dropped counts), the selected index, certificate
load start/finish/timeout/error, PIN requests and why one was refused, and the
source of every cancellation. Every error dialog is logged at warning level
with the same code. Only counts, reason codes, and the verified sign-in host
are logged; PKCS #11 URIs, labels, serials, PINs, tokens, and callback URLs
never are. The launcher exports `G_MESSAGES_DEBUG=remmina` (unless already
set) because `REMMINA_PLUGIN_DEBUG` is `g_debug()` and GLib drops the domain
otherwise; the helper writes the same output, redacted, to
`$XDG_STATE_HOME/eitaas-remmina/logs/session-*.log`, and Remmina itself also
appends debug lines to `$TMPDIR/remmina_log_file.log`.

Certificate discovery lists every PKCS #11 token, skips p11-kit's trust
tokens (`model=p11-kit-trust`), and treats a token for which
`p11tool --list-certs --only-urls` prints no URL and exits non-zero as
empty (`discovery-token-empty`) rather than as a failure; token-listing
failures, cancellation, output limits, URL output with a non-zero exit, and a
tool killed by a signal remain fatal. The full reason-code table is in the top-level README under
"Troubleshooting":

| Code | Level | Meaning |
|---|---|---|
| `challenge-received (scheme= unverified-host= port= proxy= retry= application= remote=)` | debug | WebKit asked for a client certificate or PIN; the host is the one WebKit reported, before validation |
| `challenge-accepted (host=)` | debug | The challenge origin matched the verified sign-in authority |
| `origin-rejected (reason)` | warning | Challenge refused: `proxy-challenge`, `no-authentication-host`, `no-security-origin`, `origin-not-https`, `origin-host-mismatch`, `host-not-authority`, `origin-port` |
| `discovery-tool-missing: …` | warning | `p11tool` is not installed (package `gnutls-utils`/`gnutls-bin`); the dialog names the package |
| `discovery-start (tool=)` | debug | `p11tool` enumeration started on a worker thread |
| `discovery-token-skipped-trust (count=)` | debug | p11-kit trust tokens (`model=p11-kit-trust`) skipped without a subprocess |
| `discovery-token-empty (count= last-exit=)` | debug | Tokens where `p11tool --list-certs` printed no URL and exited non-zero (no certificate on that token) |
| `discovery-finished (tokens= certificates= label-filter kept= dropped=)` | debug | Enumeration done; counts only (`label-filter` is downstream-only) |
| `discovery-busy` | warning | Another discovery was still running |
| `discovery-empty: …` | warning | No selectable certificate; the "No usable smart-card authentication certificates" dialog |
| `discovery-timeout` / `discovery-error: …` | warning | `p11tool` deadline (15 s) or failure (token listing failed, output/URI/count limits, malformed output) |
| `discovery-cancelled (user|window-closed|error-after-close)` / `discovery-result-discarded` | warning | Discovery abandoned; the one-shot client then quits (`oneshot-quit`) |
| `certificate-selected (index= of )` / `certificate-submitted (host=)` | debug | Choice made and presented to WebKit |
| `selection-cancelled (user|window-closed)` | warning | Certificate dialog dismissed |
| `load-start` / `load-finished` | debug | `GTlsCertificate` load off the GTK thread |
| `load-timeout` / `load-error (domain/code: message)` / `load-cancelled` / `load-result-discarded` | warning / debug | Load outcome; error text is cut before any `pkcs11:` URI |
| `pin-requested (host= retry=)` / `pin-submitted (host=)` | debug | PIN prompt shown and answered (the PIN itself is never logged) |
| `pin-rejected (reason)` | warning | `origin-rejected`, `no-certificate-transaction`, `transaction-expired`, `transaction-host-mismatch`, `pin-already-submitted` |
| `pin-cancelled (user|window-closed|transaction-cleared)` | warning | PIN dialog dismissed |
| `oneshot-quit (application=)` | debug | The one-shot client is quitting after a cancelled discovery |

The RDP plugin also logs the Azure Virtual Desktop ARM gateway phase with an
`avd-arm:` prefix: `avd-arm: response-timeout-ms=60000` (debug) records that
the wait for the ARM gateway's connection response was raised from FreeRDP's
15 s default to 60 s because the profile set no timeout of its own (the ARM
connection request is not idempotent and is never re-sent). The launcher sets
no `WLOG_LEVEL` or `WLOG_FILTER`: FreeRDP reports the failure this fix is about
at its default level (`timeout [<n>ms] exceeded` at ERROR from
`com.freerdp.core.gateway.http`, plus `arm.c`'s own ERROR lines), while raising
the level to DEBUG would make `com.freerdp.utils.http` log the entire OAuth
token request body and token-endpoint response — the authorization code and the
access, refresh, and id tokens.

## Authentication path and build flags

All three recipes (`packaging/rpm/eitaas-linux.spec`,
`packaging/debian/rules`, `packaging/arch/PKGBUILD`) build FreeRDP and Remmina
with `-DWITH_SSO_MIB=OFF`,
`-DWITH_AAD=ON`/`-DWITH_RDP_AUTH_AAD=ON`, and `-DWITH_PCSC=ON`, and none of
them declares an `sso-mib` build or runtime dependency; the flags are asserted
by `tests/test_remmina_packaging.py`. The Microsoft Identity Broker route was
never hardware-validated on a sovereign cloud and only exists on Intune-
enrolled devices, so it was dropped (#77). The embedded WebKitGTK CAC WebView
is therefore the only non-terminal authentication path compiled into every
package; the terminal URL/callback fallback remains refused. Turning SSO-MIB
back on is a support-matrix change that needs a hardware result and a matching
update to `docs/supported-platforms.md`, not a packaging tweak.

## Licensing and corresponding source

This is a composite binary package, not a relicensing of Remmina or FreeRDP.
Remmina and the EITaaS CAC integration compiled into its RDP plugin are
GPL-2.0-or-later; the Remmina OpenSSL exception is shipped with the package.
FreeRDP is Apache-2.0, and the standalone EITaaS launcher is MIT. See
`THIRD_PARTY_NOTICES.md` for the component map and exact pinned sources.

The source RPM, Debian source package, and Arch corresponding-source tarball
are buildable source distributions for this prototype. Each contains both
pinned upstream archives, all downstream patches, the CAC integration sources,
launcher, the Python `eitaas`/`eitaas_gui` sources, license texts, notice
manifest, and native packaging metadata. Rebuilding still downloads normal
distribution build dependencies; it does not fetch either application source
tree.
