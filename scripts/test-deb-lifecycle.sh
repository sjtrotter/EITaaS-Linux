#!/bin/sh
# Install, upgrade-from-split-packages, smoke-test, and remove the combined
# eitaas-linux DEB in a container. Run as root.
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: test-deb-lifecycle.sh PACKAGE.deb" >&2
  exit 2
fi

package=$(readlink -f -- "$1")
expected_version=$(dpkg-deb -f "$package" Version)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM

# Official minimal container images may configure dpkg to path-exclude most
# documentation at install time. Verify package payload compliance directly.
dpkg-deb --fsys-tarfile "$package" | tar -tf - >"$work/package-files.txt"
for path in \
  ./usr/bin/eitaas \
  ./usr/bin/eitaas-gui \
  ./usr/bin/eitaas-remmina \
  ./usr/lib/eitaas-remmina/bin/remmina \
  ./usr/lib/eitaas-remmina/lib/remmina/plugins/remmina-plugin-rdp.so \
  ./usr/share/applications/org.eitaas.Helper.desktop \
  ./usr/share/mime/packages/eitaas-rdpw.xml \
  ./usr/share/man/man1/eitaas.1.gz \
  ./usr/share/man/man1/eitaas-gui.1.gz \
  ./usr/share/doc/eitaas-linux/sources.json \
  ./usr/share/doc/eitaas-linux/THIRD_PARTY_NOTICES.md \
  ./usr/share/doc/eitaas-linux/licenses/Remmina-COPYING \
  ./usr/share/doc/eitaas-linux/licenses/FreeRDP-LICENSE
do
  grep -qx -- "$path" "$work/package-files.txt" ||
    { echo "missing from package payload: $path" >&2; exit 1; }
done

# Stand in for the pre-#80 world with the exact versions those packages last
# shipped, so tightening Breaks/Replaces to a narrower range fails this test
# instead of silently stranding a real installation. None of them carried
# Breaks/Replaces/Provides, and all three were Architecture: all, so the
# transition to an architecture-specific package is exercised too.
LAST_EITAAS_LINUX=0.1.0-1
LAST_EITAAS_REMMINA=1.4.43+eitaas0.15

stub() {
  rm -rf "$work/stub"
  mkdir -p "$work/stub/DEBIAN" "$work/stub/usr/share/doc/$1"
  echo 'superseded by eitaas-linux' >"$work/stub/usr/share/doc/$1/README"
  {
    echo "Package: $1"
    echo "Version: $2"
    echo 'Architecture: all'
    echo 'Maintainer: EITaaS-Linux contributors <sjtrotter@users.noreply.github.com>'
    echo 'Description: superseded split package used only by the lifecycle test'
    echo ' Stands in for the pre-#80 binary package of the same name.'
  } >"$work/stub/DEBIAN/control"
  dpkg-deb --build "$work/stub" "$work/$1-old.deb" >/dev/null
}
stub eitaas-linux "$LAST_EITAAS_LINUX"
stub eitaas-remmina "$LAST_EITAAS_REMMINA"
stub eitaas-linux-gui "$LAST_EITAAS_LINUX"

apt-get install -y "$work/eitaas-linux-old.deb" "$work/eitaas-remmina-old.deb" \
  "$work/eitaas-linux-gui-old.deb" >/dev/null
test "$(dpkg-query -W -f='${Version}' eitaas-linux)" = "$LAST_EITAAS_LINUX"

# Breaks/Replaces/Provides must retire both split packages on upgrade.
apt-get install -y "$package" >/dev/null
test "$(dpkg-query -W -f='${Version}' eitaas-linux)" = "$expected_version"
for superseded in eitaas-remmina eitaas-linux-gui; do
  if [ "$(dpkg-query -W -f='${db:Status-Status}' "$superseded" 2>/dev/null || true)" = installed ]; then
    echo "$superseded is still installed after the upgrade" >&2
    exit 1
  fi
done

test -x /usr/bin/eitaas-remmina
test -x /usr/lib/eitaas-remmina/bin/remmina
test -f /usr/lib/eitaas-remmina/lib/remmina/plugins/remmina-plugin-rdp.so
ldd /usr/lib/eitaas-remmina/bin/remmina | tee "$work/ldd.txt"
if grep -q 'not found' "$work/ldd.txt"; then
  echo 'unresolved runtime library in installed package' >&2
  exit 1
fi

eitaas --version
eitaas-gui --version
status=0
eitaas doctor --json >"$work/doctor.json" || status=$?
test "$status" -eq 0 -o "$status" -eq 1
test -f /usr/share/applications/org.eitaas.Helper.desktop
desktop-file-validate /usr/share/applications/org.eitaas.Helper.desktop

apt-get remove -y eitaas-linux >/dev/null
if [ "$(dpkg-query -W -f='${db:Status-Status}' eitaas-linux 2>/dev/null || true)" = installed ]; then
  echo 'package remains installed after removal' >&2
  exit 1
fi
