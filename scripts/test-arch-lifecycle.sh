#!/bin/sh
# Install, upgrade, smoke-test, and remove the combined eitaas-linux Arch
# package in a container. Run as root.
#
# There is no upgrade-from-split-packages step here: pacman honours
# `replaces` only for a repository transaction (`pacman -Sy`), never for the
# local `pacman -U` a container test can perform, so the split-to-combined
# path is covered by the DEB and RPM lifecycle tests. The `conflicts`,
# `replaces`, and `provides` entries in packaging/arch/PKGBUILD are asserted
# by tests/test_remmina_packaging.py.
set -eu

package=${1:?usage: test-arch-lifecycle.sh PACKAGE}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM

bsdtar -tf "$package" >"$work/package-files.txt"
current_version=$(bsdtar -xOf "$package" .PKGINFO | sed -n 's/^pkgver = //p')
prior_version=${current_version%-*}-0
for path in \
  usr/bin/eitaas \
  usr/bin/eitaas-gui \
  usr/bin/eitaas-remmina \
  usr/lib/eitaas-remmina/bin/remmina \
  usr/lib/eitaas-remmina/lib/remmina/plugins/remmina-plugin-rdp.so \
  usr/share/applications/org.eitaas.Helper.desktop \
  usr/share/mime/packages/eitaas-rdpw.xml \
  usr/share/man/man1/eitaas.1 \
  usr/share/man/man1/eitaas-gui.1 \
  usr/share/doc/eitaas-linux/sources.json \
  usr/share/licenses/eitaas-linux/THIRD_PARTY_NOTICES.md \
  usr/share/licenses/eitaas-linux/Remmina-COPYING \
  usr/share/licenses/eitaas-linux/FreeRDP-LICENSE
do
  grep -qx -- "$path" "$work/package-files.txt" ||
    { echo "missing from package payload: $path" >&2; exit 1; }
done

mkdir "$work/old"
bsdtar -xf "$package" -C "$work/old"
sed -i "s/^pkgver = .*/pkgver = $prior_version/" "$work/old/.PKGINFO"
(cd "$work/old" && bsdtar --uid 0 --gid 0 -cf - .PKGINFO .BUILDINFO .MTREE usr) \
  | zstd -q -o "$work/eitaas-linux-old.pkg.tar.zst"

pacman -U --noconfirm "$work/eitaas-linux-old.pkg.tar.zst"
test "$(pacman -Q eitaas-linux)" = "eitaas-linux $prior_version"
pacman -U --noconfirm "$package"
test "$(pacman -Q eitaas-linux)" = "eitaas-linux $current_version"

test -x /usr/bin/eitaas-remmina
test -x /usr/lib/eitaas-remmina/bin/remmina
test -f /usr/lib/eitaas-remmina/lib/remmina/plugins/remmina-plugin-rdp.so
ldd /usr/lib/eitaas-remmina/bin/remmina | tee "$work/ldd.txt"
! grep -q 'not found' "$work/ldd.txt"

eitaas --version
eitaas-gui --version
status=0
eitaas doctor --json >"$work/doctor.json" || status=$?
test "$status" -eq 0 -o "$status" -eq 1
test -f /usr/share/applications/org.eitaas.Helper.desktop
desktop-file-validate /usr/share/applications/org.eitaas.Helper.desktop

pacman -R --noconfirm eitaas-linux
! pacman -Q eitaas-linux
