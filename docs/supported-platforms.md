# Supported platforms

AVD connections require FreeRDP 3 compiled with AAD and PC/SC support. Package
names alone are not treated as proof; `eitaas doctor` checks build capabilities.

Ubuntu 22.04 is not supported by the distribution dependency path because its
standard repositories provide FreeRDP 2. Current Ubuntu and Fedora releases are
candidate targets and must pass CI plus the manual release matrix.

Under Wayland, automatic selection prefers a compatible XFreeRDP client through
XWayland. SDL and native Wayland backends remain explicit choices until they
pass the same AVD and smart-card tests.
