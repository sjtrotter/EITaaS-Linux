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

Ubuntu 22.04 is not supported by the distribution dependency path because its
standard repositories provide FreeRDP 2. Current Ubuntu and Fedora releases are
candidate targets and must pass CI plus the manual release matrix. The isolated
SDL/WebView authentication client has passed its Azure Government, PIV, and
CAC-redirection hardware gates only on Fedora 44. Its current package recipe is
RPM-specific.

Arch Linux is also a candidate target. The upstream `PKGBUILD` pins a reviewed
source revision and checksum and depends only on official repository packages.
It is not an official Arch repository or AUR package. Arch currently ships
FreeRDP 3 clients, including X11, Wayland, and SDL variants, but `eitaas doctor`
must still confirm AAD, PC/SC, and a secure non-terminal authentication path at
runtime. The Fedora WebView RPM is not installed by the Arch package.

Under Wayland, automatic selection first requires secure authentication. A live
identity broker permits the normal X11, SDL, then Wayland preference; without a
broker, a WebView-enabled SDL client is selected. Native Wayland remains an
explicit choice until it passes the same AVD and smart-card tests. The Fedora
44 GNOME Wayland test succeeded through XWayland, but multimonitor scaling and
pointer alignment remain unsupported pending issue #29.
