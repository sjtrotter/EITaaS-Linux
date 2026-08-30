# Isolated Remmina prototype

All packaging formats must consume the pinned source and ordered patch data in
`sources.json`. The cross-distribution delivery decision and validation matrix
are recorded in `docs/adr/0001-remmina-packaging-strategy.md`.

This package combines a private Remmina 1.4.43 build with private FreeRDP
3.31.0 libraries under `/usr/libexec/eitaas-remmina`. It does not replace the
distribution packages.

The downstream changes preserve the original protected RDPW profile through
FreeRDP's parser, select ARM/AAD transport, honor smart-card redirection, and
handle WebKitGTK client-certificate and PIN challenges with PKCS #11-backed
CAC credentials. Only authentication, identity, and PIV-labelled certificates
are shown. Certificate discovery runs on a worker while a cancellable progress
dialog keeps the GTK interface responsive. Cancelling discovery ends the
containing AVD authentication attempt. Core dumps are disabled before opening
the authentication view.

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

Build conservatively with `RPM_BUILD_NCPUS=1` and `_smp_build_ncpus 1`.
After installation, launch only through:

```console
eitaas-remmina "$HOME/Downloads/Desktop.rdpw"
```

This command is a one-shot connection: cancelling CAC authentication closes
the authentication flow and the isolated Remmina application instead of
leaving its connection manager open. A future no-argument manager mode is
tracked separately and will intentionally remain open between connections.

The launcher uses an isolated configuration directory below
`$XDG_STATE_HOME/eitaas-remmina` (or `~/.local/state/eitaas-remmina`) so user
plugins and settings from the distribution Remmina installation are not mixed
with the prototype.

## Licensing and corresponding source

This is a composite binary package, not a relicensing of Remmina or FreeRDP.
Remmina and the EITaaS CAC integration compiled into its RDP plugin are
GPL-2.0-or-later; the Remmina OpenSSL exception is shipped with the package.
FreeRDP is Apache-2.0, and the standalone EITaaS launcher is MIT. See
`THIRD_PARTY_NOTICES.md` for the component map and exact pinned sources.

The source RPM is the corresponding, buildable source distribution for this
prototype. It contains both pinned upstream archives, all downstream patches,
the CAC integration sources, launcher, license texts, notice manifest, and the
RPM spec. Rebuilding still downloads normal Fedora build dependencies; it does
not fetch either application source tree.
