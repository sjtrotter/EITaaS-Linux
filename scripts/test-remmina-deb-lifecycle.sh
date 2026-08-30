#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: test-remmina-deb-lifecycle.sh PACKAGE.deb" >&2
  exit 2
fi

package=$(readlink -f -- "$1")
expected_version=$(dpkg-deb -f "$package" Version)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM

# Official minimal container images may configure dpkg to path-exclude most
# documentation at install time. Verify package payload compliance directly.
dpkg-deb --fsys-tarfile "$package" | tar -tf - >"$work/package-files.txt"
grep -q './usr/share/doc/eitaas-remmina/sources.json' "$work/package-files.txt"
grep -q './usr/share/doc/eitaas-remmina/THIRD_PARTY_NOTICES.md' "$work/package-files.txt"
grep -q './usr/share/doc/eitaas-remmina/licenses/Remmina-COPYING' "$work/package-files.txt"

# Synthesize the "already installed" package from the one under test rather
# than pinning a version string a manifest already owns. A "~" suffix always
# sorts before the unsuffixed version in Debian's comparison, so the upgrade
# below is a genuine upgrade for whatever the changelog currently records.
prior_version="$expected_version~0"

dpkg-deb --raw-extract "$package" "$work/old"
sed -i "s/^Version: .*/Version: $prior_version/" "$work/old/DEBIAN/control"
dpkg-deb --build "$work/old" "$work/eitaas-remmina-old.deb" >/dev/null

apt-get install -y "$work/eitaas-remmina-old.deb" >/dev/null
test "$(dpkg-query -W -f='${Version}' eitaas-remmina)" = "$prior_version"

apt-get install -y "$package" >/dev/null
test "$(dpkg-query -W -f='${Version}' eitaas-remmina)" = "$expected_version"
test -x /usr/bin/eitaas-remmina
test -f /usr/lib/eitaas-remmina/lib/remmina/plugins/remmina-plugin-rdp.so
ldd /usr/lib/eitaas-remmina/bin/remmina | tee "$work/ldd.txt"
if grep -q 'not found' "$work/ldd.txt"; then
  echo 'unresolved runtime library in installed package' >&2
  exit 1
fi

apt-get remove -y eitaas-remmina >/dev/null
if [ "$(dpkg-query -W -f='${db:Status-Status}' eitaas-remmina 2>/dev/null || true)" = installed ]; then
  echo 'package remains installed after removal' >&2
  exit 1
fi
