# Supported platforms

AVD connections require FreeRDP 3 compiled with AAD and PC/SC support. Package
names alone are not treated as proof; `eitaas doctor` checks build capabilities.

Ubuntu 22.04 is not supported by the distribution dependency path because its
standard repositories provide FreeRDP 2. Current Ubuntu and Fedora releases are
candidate targets and must pass CI plus the manual release matrix.

Arch Linux is also a candidate target. The upstream `PKGBUILD` pins a reviewed
source revision and checksum and depends only on official repository packages.
It is not an official Arch repository or AUR package. Arch currently ships
FreeRDP 3 clients, including X11, Wayland, and SDL variants, but `eitaas doctor`
must still confirm AAD and PC/SC capabilities at runtime.

Under Wayland, automatic selection prefers a compatible XFreeRDP client through
XWayland. SDL and native Wayland backends remain explicit choices until they
pass the same AVD and smart-card tests.
