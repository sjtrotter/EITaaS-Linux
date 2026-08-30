#!/bin/sh
# Build the combined eitaas-linux Arch package. The corresponding-source
# tarball carries the repository sources plus both verified upstream archives
# with the ordered patch series from packaging/remmina/sources.json already
# applied; the PKGBUILD downloads nothing.
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=${EITAAS_BUILD_ROOT:-"$project_root/.build/eitaas-bundle"}
cache="$build_root/cache"
package_dir="$project_root/packaging/arch"
source_archive=${1:-}

if [ "$(id -u)" -eq 0 ]; then
    echo 'makepkg must run as an unprivileged user' >&2
    exit 1
fi

version=$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "$project_root/pyproject.toml")
source_root="$build_root/eitaas-linux-$version-source"
archive="$build_root/eitaas-linux-$version-source.tar.gz"
stage="$build_root/package"

mkdir -p "$cache" "$project_root/dist"
rm -rf "$source_root" "$stage"
if [ -n "$source_archive" ]; then
    "$project_root/scripts/prepare-bundle-source.py" --project-root "$project_root" \
        tree --cache "$cache" --output "$source_root" --source-archive "$source_archive"
else
    "$project_root/scripts/prepare-bundle-source.py" --project-root "$project_root" \
        tree --cache "$cache" --output "$source_root"
fi

tar --sort=name --mtime='UTC 2026-08-30' --owner=0 --group=0 --numeric-owner \
    -czf "$archive" -C "$source_root" .
checksum=$(sha256sum "$archive" | cut -d ' ' -f 1)

mkdir -p "$stage"
cp "$package_dir/PKGBUILD" "$stage/PKGBUILD"
cp "$archive" "$stage/eitaas-linux-$version-source.tar.gz"
sed -i "s/@SHA256@/$checksum/" "$stage/PKGBUILD"
(cd "$stage" && MAKEFLAGS=-j1 makepkg --cleanbuild --force)
find "$stage" -maxdepth 1 -type f -name '*.pkg.tar.*' -exec cp {} "$project_root/dist/" \;
