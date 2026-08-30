# Supported platforms

The delivery decision, exact enhanced-client support boundary, and required
CI/hardware matrix are defined in
[`docs/adr/0001-remmina-packaging-strategy.md`](adr/0001-remmina-packaging-strategy.md).
Native packages are the baseline; portable formats are not currently supported.

AVD connections use only the bundled `eitaas-remmina` client, built from the
pins in `packaging/remmina/sources.json` with AAD and PC/SC support. The
`eitaas-linux` helper package declares a weak dependency on it (`Recommends`
on DEB and RPM, `optdepends` on Arch). `eitaas doctor` reports whether the
launcher and private client are installed and the pinned versions from the
installed manifest; distribution FreeRDP packages are not consulted.

The only supported authentication path is the embedded CAC WebView. The
terminal URL/callback fallback is refused inside the bundled client, and the
Microsoft Identity Broker (SSO-MIB) route is not compiled in anywhere:
`packaging/remmina/eitaas-remmina.spec`, `packaging/remmina/debian/rules`, and
`packaging/remmina/arch/PKGBUILD` all build FreeRDP and Remmina with
`-DWITH_SSO_MIB=OFF` (asserted by `tests/test_remmina_packaging.py`, explained
in `packaging/remmina/README.md`).

The Remmina patches require the FreeRDP 3.16 settings API
(`FreeRDP_GatewayAvdScope`, `FreeRDP_GatewayAvdAccessAadFormat`); the bundle
pins and is tested with the FreeRDP 3.30.x line. Distribution FreeRDP versions
recorded on 2026-08-30 (#77): Fedora 43/44 3.30.0, Ubuntu 26.04 3.24.2 (3.30.0
in updates), Arch 3.31.0, Debian 13 3.15.0 (3.26/3.30 in backports), Ubuntu
24.04 3.5.1. Linking a patched Remmina against a distribution FreeRDP is
therefore feasible on Fedora, Ubuntu 26.04, and Arch but not on Debian 13 or
Ubuntu 24.04; the private bundle remains the delivery for every target until
that simplification is taken up separately.

Ubuntu 22.04 is not a target: the bundled client's build dependencies are
taken from the distribution and the DEB recipe is validated only on Ubuntu
24.04 and Debian 13. Those two and current Fedora releases are candidate
targets and must pass CI plus the manual release matrix. Native DEBs for
Ubuntu 24.04 and Debian 13 are built from the shared pinned-source manifest
and pass clean install, upgrade, linkage, and removal checks in containers.
The bundled client has passed its Azure Government, PIV, and CAC-redirection
hardware gates only on Fedora 44; successful DEB packaging does not yet
establish runtime or hardware support on Ubuntu or Debian.

Arch Linux is also a candidate target. The upstream `PKGBUILD` pins a reviewed
source revision and checksum and depends only on official repository packages.
It is not an official Arch repository or AUR package.

The isolated enhanced Remmina package is also built against the repository
snapshot recorded in `packaging/remmina/arch/SNAPSHOT`. It consumes the shared
pinned-source manifest and installs its private client under
`/usr/lib/eitaas-remmina`; successful package CI does not establish Arch CAC
hardware support.

The bundled Remmina client is a GTK 3 application; the Fedora 44 GNOME
Wayland test succeeded through XWayland, but multimonitor scaling and pointer
alignment remain unsupported pending issue #29.
