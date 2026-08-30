# Supported platforms

The delivery decision, exact enhanced-client support boundary, and required
CI/hardware matrix are defined in
[`docs/adr/0001-remmina-packaging-strategy.md`](adr/0001-remmina-packaging-strategy.md).
Native packages are the baseline; portable formats are not currently supported.

AVD connections require FreeRDP 3 compiled with AAD and PC/SC support plus a
non-terminal authentication path. Package names alone are not treated as
proof; `eitaas doctor` checks build capabilities and the live broker.

Supported authentication paths are a Microsoft Identity Broker reachable over
D-Bus by a FreeRDP SSO-MIB build, or an SDL FreeRDP client built with WebView.
AAD without either path is reported as unavailable because FreeRDP otherwise
falls back to printing an authorization URL and reading a callback from the
terminal.

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

Ubuntu 22.04 is not supported by the distribution dependency path because its
standard repositories provide FreeRDP 2. Ubuntu 24.04, Debian 13, and current
Fedora releases are candidate targets and must pass CI plus the manual release
matrix. Native DEBs for Ubuntu 24.04 and Debian 13 are built from the shared
pinned-source manifest and pass clean install, upgrade, linkage, and removal
checks in containers. The isolated SDL/WebView authentication client has passed
its Azure Government, PIV, and CAC-redirection hardware gates only on Fedora
44; successful DEB packaging does not yet establish runtime or hardware
support on Ubuntu or Debian.

Arch Linux is also a candidate target. The upstream `PKGBUILD` pins a reviewed
source revision and checksum and depends only on official repository packages.
It is not an official Arch repository or AUR package. Arch currently ships
FreeRDP 3 clients, including X11, Wayland, and SDL variants, but `eitaas doctor`
must still confirm AAD, PC/SC, and a secure non-terminal authentication path at
runtime. The Fedora WebView RPM is not installed by the Arch package.

The isolated enhanced Remmina package is also built against the repository
snapshot recorded in `packaging/remmina/arch/SNAPSHOT`. It consumes the shared
pinned-source manifest and installs its private client under
`/usr/lib/eitaas-remmina`; successful package CI does not establish Arch CAC
hardware support.

Under Wayland, automatic selection first requires secure authentication. A live
identity broker permits the normal X11, SDL, then Wayland preference; without a
broker, a WebView-enabled SDL client is selected. Native Wayland remains an
explicit choice until it passes the same AVD and smart-card tests. The Fedora
44 GNOME Wayland test succeeded through XWayland, but multimonitor scaling and
pointer alignment remain unsupported pending issue #29.
