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

dpkg-deb --raw-extract "$package" "$work/old"
sed -i 's/^Version: .*/Version: 1.4.43+eitaas0.7/' "$work/old/DEBIAN/control"
dpkg-deb --build "$work/old" "$work/eitaas-remmina-old.deb" >/dev/null

apt-get install -y "$work/eitaas-remmina-old.deb" >/dev/null
test "$(dpkg-query -W -f='${Version}' eitaas-remmina)" = '1.4.43+eitaas0.7'

apt-get install -y "$package" >/dev/null
test "$(dpkg-query -W -f='${Version}' eitaas-remmina)" = "$expected_version"
test -x /usr/bin/eitaas-remmina
test -f /usr/lib/eitaas-remmina/lib/remmina/plugins/remmina-plugin-rdp.so
test -f /usr/share/doc/eitaas-remmina/sources.json \
  || test -f /usr/share/doc/eitaas-remmina/sources.json.gz
grep -q '/usr/lib/eitaas-remmina/bin/remmina' /usr/bin/eitaas-remmina
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
