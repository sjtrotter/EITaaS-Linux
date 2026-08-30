#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=${EITAAS_REMMINA_ARCH_BUILD_ROOT:-"$project_root/.build/eitaas-remmina-arch"}
package_dir="$project_root/packaging/remmina"

if [ "$(id -u)" -eq 0 ]; then
  echo 'makepkg must run as an unprivileged user' >&2
  exit 1
fi

pkgver=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["package_version"])' \
  "$package_dir/sources.json")
source_root="$build_root/eitaas-remmina-$pkgver-source"
archive="$build_root/eitaas-remmina-$pkgver-source.tar.gz"
stage="$build_root/package"
mkdir -p "$build_root/cache" "$project_root/dist"
rm -rf "$source_root" "$stage"
"$project_root/scripts/prepare-remmina-deb-source.py" \
  --project-root "$project_root" --cache "$build_root/cache" --output "$source_root"
tar --sort=name --mtime='UTC 2026-08-30' --owner=0 --group=0 --numeric-owner \
  -czf "$archive" -C "$source_root" .
checksum=$(sha256sum "$archive" | cut -d ' ' -f 1)
mkdir -p "$stage"
cp "$package_dir/arch/PKGBUILD" "$stage/PKGBUILD"
cp "$archive" "$stage/eitaas-remmina-$pkgver-source.tar.gz"
sed -i -e "s/@PKGVER@/$pkgver/" -e "s/@SHA256@/$checksum/" "$stage/PKGBUILD"
(cd "$stage" && MAKEFLAGS=-j1 makepkg --cleanbuild --force)
find "$stage" -maxdepth 1 -type f -name '*.pkg.tar.*' -exec cp {} "$project_root/dist/" \;
