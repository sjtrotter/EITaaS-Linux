#!/bin/sh
set -eu

package=${1:?usage: test-remmina-arch-lifecycle.sh PACKAGE}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM

bsdtar -tf "$package" >"$work/package-files.txt"
current_version=$(bsdtar -xOf "$package" .PKGINFO | sed -n 's/^pkgver = //p')
prior_version=${current_version%-*}-0
grep -q 'usr/share/doc/eitaas-remmina/sources.json' "$work/package-files.txt"
grep -q 'usr/share/licenses/eitaas-remmina/THIRD_PARTY_NOTICES.md' "$work/package-files.txt"
grep -q 'usr/share/licenses/eitaas-remmina/Remmina-COPYING' "$work/package-files.txt"

mkdir "$work/old"
bsdtar -xf "$package" -C "$work/old"
sed -i "s/^pkgver = .*/pkgver = $prior_version/" "$work/old/.PKGINFO"
(cd "$work/old" && bsdtar --uid 0 --gid 0 -cf - .PKGINFO .BUILDINFO .MTREE usr) \
  | zstd -q -o "$work/eitaas-remmina-old.pkg.tar.zst"

pacman -U --noconfirm "$work/eitaas-remmina-old.pkg.tar.zst"
test "$(pacman -Q eitaas-remmina)" = "eitaas-remmina $prior_version"
pacman -U --noconfirm "$package"
test "$(pacman -Q eitaas-remmina)" = "eitaas-remmina $current_version"
test -x /usr/bin/eitaas-remmina
test -x /usr/lib/eitaas-remmina/bin/remmina
test -f /usr/lib/eitaas-remmina/lib/remmina/plugins/remmina-plugin-rdp.so
ldd /usr/lib/eitaas-remmina/bin/remmina | tee "$work/ldd.txt"
! grep -q 'not found' "$work/ldd.txt"
pacman -R --noconfirm eitaas-remmina
! pacman -Q eitaas-remmina
