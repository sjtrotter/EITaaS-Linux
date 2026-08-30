#!/bin/sh
# Install, upgrade-from-split-packages, smoke-test, and remove the combined
# eitaas-linux RPM in a container. Run as root; needs rpm-build for the
# stand-in packages.
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: test-rpm-lifecycle.sh PACKAGE.rpm" >&2
  exit 2
fi

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
package=$(readlink -f -- "$1")
expected_version=$(rpm -qp --queryformat '%{VERSION}-%{RELEASE}' "$package")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM

rpm -qlp "$package" >"$work/package-files.txt"
for path in \
  /usr/bin/eitaas \
  /usr/bin/eitaas-gui \
  /usr/bin/eitaas-remmina \
  /usr/libexec/eitaas-remmina/bin/remmina \
  /usr/libexec/eitaas-remmina/lib64/remmina/plugins/remmina-plugin-rdp.so \
  /usr/share/applications/org.eitaas.Helper.desktop \
  /usr/share/mime/packages/eitaas-rdpw.xml \
  /usr/share/man/man1/eitaas.1.gz \
  /usr/share/man/man1/eitaas-gui.1.gz \
  /usr/share/doc/eitaas-linux/sources.json \
  /usr/share/licenses/eitaas-linux/THIRD_PARTY_NOTICES.md \
  /usr/share/licenses/eitaas-linux/Remmina-COPYING \
  /usr/share/licenses/eitaas-linux/FreeRDP-LICENSE
do
  grep -qx -- "$path" "$work/package-files.txt" ||
    { echo "missing from package payload: $path" >&2; exit 1; }
done

# Stand in for the pre-#80 world: eitaas-remmina and eitaas-linux-gui carried
# no Obsoletes of their own, so minimal stand-ins with the versions those
# packages last shipped are enough to prove the Obsoletes in the combined spec
# retire them.
stub() {
  mkdir -p "$work/rpmbuild/SPECS"
  {
    echo "Name:           $1"
    echo "Version:        $2"
    echo "Release:        $3"
    echo 'Summary:        superseded split package used only by the lifecycle test'
    echo 'License:        MIT'
    echo 'BuildArch:      noarch'
    echo '%description'
    echo 'Stands in for the pre-#80 binary package of the same name.'
    echo '%install'
    echo "install -Dpm 0644 /dev/null %{buildroot}%{_docdir}/$1/README"
    echo '%files'
    echo "%{_docdir}/$1/README"
    echo '%changelog'
  } >"$work/rpmbuild/SPECS/$1.spec"
  rpmbuild --define "_topdir $work/rpmbuild" --define 'dist %{nil}' \
    -bb "$work/rpmbuild/SPECS/$1.spec" >/dev/null
}
# The superseded bundle version is recorded in the shared manifest; the
# stand-in release sorts below the Obsoletes bound in the combined spec.
remmina_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["package_version"])' \
  "$project_root/packaging/remmina/sources.json")
stub eitaas-remmina "$remmina_version" 0
stub eitaas-linux-gui "${expected_version%-*}" 0

dnf install -y "$work"/rpmbuild/RPMS/noarch/eitaas-remmina-*.rpm \
  "$work"/rpmbuild/RPMS/noarch/eitaas-linux-gui-*.rpm >/dev/null
rpm -q eitaas-remmina eitaas-linux-gui

# Obsoletes/Provides must retire both split packages on install.
dnf install -y "$package" >/dev/null
test "$(rpm -q --queryformat '%{VERSION}-%{RELEASE}' eitaas-linux)" = "$expected_version"
for superseded in eitaas-remmina eitaas-linux-gui; do
  if rpm -q "$superseded" >/dev/null 2>&1; then
    echo "$superseded is still installed after the upgrade" >&2
    exit 1
  fi
done

test -x /usr/bin/eitaas-remmina
test -x /usr/libexec/eitaas-remmina/bin/remmina
test -f /usr/libexec/eitaas-remmina/lib64/remmina/plugins/remmina-plugin-rdp.so
ldd /usr/libexec/eitaas-remmina/bin/remmina | tee "$work/ldd.txt"
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

dnf remove -y eitaas-linux >/dev/null
if rpm -q eitaas-linux >/dev/null 2>&1; then
  echo 'package remains installed after removal' >&2
  exit 1
fi
