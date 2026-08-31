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
package_version=${current_version%-*}
prior_version=$package_version-0

# Arch has no `~` pre-release marker, so packaging/arch/PKGBUILD keeps the
# canonical PEP 440 pkgver (X.Y.ZrcN) where RPM and Debian spell the same
# release X.Y.Z~rcN. pacman must still sort a pre-release BELOW the final
# release of the same base version, or the eventual final would not upgrade
# over its candidates (issue #95). This is the one place a real vercmp exists,
# so assert the guarantee here instead of documenting it and hoping.
base_version=$(printf '%s\n' "$package_version" | sed -E 's/(a|b|rc)[0-9]+$//')
if [ "$base_version" != "$package_version" ]; then
  test "$(vercmp "$package_version" "$base_version")" -lt 0 ||
    { echo "pacman does not sort $package_version below $base_version" >&2; exit 1; }
  test "$(vercmp "$base_version" "$package_version")" -gt 0 ||
    { echo "pacman does not sort $base_version above $package_version" >&2; exit 1; }
fi

for path in \
  usr/bin/eitaas \
  usr/bin/eitaas-gui \
  usr/bin/eitaas-remmina \
  usr/lib/eitaas-remmina/bin/remmina \
  usr/lib/eitaas-remmina/lib/remmina/plugins/remmina-plugin-rdp.so \
  usr/share/applications/org.eitaas.Helper.desktop \
  usr/share/mime/packages/eitaas-rdpw.xml \
  usr/share/man/man1/eitaas.1.gz \
  usr/share/man/man1/eitaas-gui.1.gz \
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
