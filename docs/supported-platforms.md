# Supported platforms

The delivery decision, exact enhanced-client support boundary, and required
CI/hardware matrix are defined in
[`docs/adr/0001-remmina-packaging-strategy.md`](adr/0001-remmina-packaging-strategy.md).
Native packages are the baseline; portable formats are not currently supported.

AVD connections use only the bundled `eitaas-remmina` client, built from the
pins in `packaging/remmina/sources.json` with AAD and PC/SC support. The
`eitaas-linux` helper package declares a weak dependency on it (`Recommends`
on DEB and RPM, `optdepends` on Arch). `eitaas doctor` reports whether the
launcher and private client are installed, the pinned versions from the
installed manifest, and whether the bundle links SSO-MIB; distribution FreeRDP
packages are not consulted.

Supported authentication paths are a Microsoft Identity Broker reachable over
D-Bus (SSO-MIB build) or the embedded CAC WebView. The terminal URL/callback
fallback is refused inside the bundled client.

The isolated enhanced Remmina package does not offer both paths everywhere.
`packaging/remmina/eitaas-remmina.spec` builds FreeRDP and Remmina with
`-DWITH_SSO_MIB=ON`, while `packaging/remmina/debian/rules` and
`packaging/remmina/arch/PKGBUILD` build both with `-DWITH_SSO_MIB=OFF`. The
identity-broker route is therefore compiled into the Fedora RPM only; on the
DEB and Arch packages the embedded WebKitGTK CAC WebView is the only
non-terminal path compiled in. This follows the validation state: the RPM is
the bundle used for the recorded Fedora 44 hardware gates and was built with
the broker path compiled in, while the DEB and Arch packages have no hardware
results at all. Those gates were passed through the WebView; no
hardware result for the identity-broker route itself is recorded. The
per-recipe flags are asserted by `tests/test_remmina_packaging.py` and
explained in `packaging/remmina/README.md`.

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
