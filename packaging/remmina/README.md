# Isolated Remmina prototype

All packaging formats must consume the pinned source and ordered patch data in
`sources.json`. The cross-distribution delivery decision and validation matrix
are recorded in `docs/adr/0001-remmina-packaging-strategy.md`.

This package combines a private Remmina 1.4.43 build with private FreeRDP
3.31.0 libraries under a distribution-native private prefix
(`/usr/libexec/eitaas-remmina` on Fedora and `/usr/lib/eitaas-remmina` on
Debian-family systems). It does not replace the distribution packages.

FreeRDP 3.31.0 is pinned for two distinct reasons. First, it is the exact ABI
and feature baseline used for the successful GovCloud and CAC hardware tests.
Second, unlike 3.30.0, its SSO-MIB token path derives the authority from the
configured AAD endpoint and tenant instead of fixing it to commercial Azure
`common`; 3.31.0 or newer is therefore required for the sovereign-cloud
identity-broker route. The browser/CAC Remmina patches themselves use APIs
already present in 3.30.0, so upstream proposals must describe 3.31 as the
full sovereign-cloud and tested-bundle requirement, not as an artificial
compile-time minimum.

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
packaged `/usr/bin/p11tool`, a 15-second cancellation deadline, one concurrent
discovery, and explicit output/object limits. Protected profiles are limited
to 1 MiB, opened without following symlinks, retained as one immutable buffer, and parsed
from a verified bounded buffer exactly once during pre-connect initialization.

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

Build RPMs conservatively with `RPM_BUILD_NCPUS=1` and `_smp_build_ncpus 1`.
Build native DEB source and binary packages on Ubuntu 24.04 or Debian 13 with:

```console
scripts/build-remmina-deb.sh
```

The DEB builder consumes the same `sources.json`, verifies both upstream
archives, applies the same ordered patch series, and forces a single compile
job. It writes packages and corresponding source artifacts to `dist/`. These
DEBs are build- and lifecycle-tested in clean containers; Azure Government and
CAC hardware validation is still required on each distribution before either
becomes a supported runtime target.

Build the native Arch package against the repository snapshot recorded in
`arch/SNAPSHOT` with:

```console
scripts/build-remmina-arch.sh
```

The Arch builder must run unprivileged. It derives the version and complete
corresponding-source checksum from `sources.json`, forces one compile job, and
writes the package to `dist/`. Arch remains candidate-only pending its hardware
matrix.

Release and reproducibility builds use the repository date in `arch/SNAPSHOT`.
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

## SSO-MIB per distribution

The three recipes deliberately differ on one build flag, and the difference is
asserted by `tests/test_remmina_packaging.py` so it cannot drift silently.

| Recipe | FreeRDP and Remmina flag | Identity-broker route |
| --- | --- | --- |
| `eitaas-remmina.spec` (Fedora RPM) | `-DWITH_SSO_MIB=ON` | compiled in |
| `debian/rules` (Ubuntu 24.04, Debian 13) | `-DWITH_SSO_MIB=OFF` | not compiled in |
| `arch/PKGBUILD` (Arch) | `-DWITH_SSO_MIB=OFF` | not compiled in |

The RPM is the exact bundle used for the recorded Azure Government, PIV, and
CAC-redirection hardware gates on Fedora 44, and it is *built with* the
Microsoft Identity Broker path compiled in; the spec therefore also carries
`BuildRequires: sso-mib-devel`. Those gates were passed through the embedded
WebKitGTK CAC WebView. No hardware result for the identity-broker route itself
is recorded, on Fedora or anywhere else. The DEB and Arch packages are build-
and lifecycle-tested candidates that have not passed the hardware gates at all,
and neither recipe declares an `sso-mib` build or runtime dependency, so the
WebView is the only non-terminal path compiled into them.

The consequence is that today the identity-broker route is compiled in only on
the RPM, and is unvalidated even there. All three recipes build the RDP plugin
with `-DWITH_RDP_AUTH_AAD=ON`, so the embedded WebView CAC path is present in
every package. Turning either `OFF` into `ON` is a support-matrix change, not a
packaging tweak: it would compile an unvalidated broker route into a platform
that has no hardware results at all, so it belongs with the corresponding
update to `docs/supported-platforms.md`.

## Licensing and corresponding source

This is a composite binary package, not a relicensing of Remmina or FreeRDP.
Remmina and the EITaaS CAC integration compiled into its RDP plugin are
GPL-2.0-or-later; the Remmina OpenSSL exception is shipped with the package.
FreeRDP is Apache-2.0, and the standalone EITaaS launcher is MIT. See
`THIRD_PARTY_NOTICES.md` for the component map and exact pinned sources.

The source RPM, Debian source package, and Arch corresponding-source tarball
are buildable source distributions for this prototype. Each contains both
pinned upstream archives, all downstream patches, the CAC integration sources,
launcher, license texts, notice manifest, and native packaging metadata.
Rebuilding still downloads normal distribution build dependencies; it does not
fetch either application source tree.
