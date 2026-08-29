#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
package_dir="$project_root/packaging/arch"
source_archive=${1:-}

if [ "$(id -u)" -eq 0 ]; then
    echo 'makepkg must run as an unprivileged user' >&2
    exit 1
fi

if [ -n "$source_archive" ]; then
    build_dir=$(mktemp -d)
    trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
    version=$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "$project_root/pyproject.toml")
    archive_name="eitaas-linux-$version.tar.gz"
    checksum=$(sha256sum "$source_archive" | cut -d ' ' -f 1)
    cp "$package_dir/PKGBUILD" "$build_dir/PKGBUILD"
    cp "$source_archive" "$build_dir/$archive_name"
    sed -i \
        -e "s|^source=.*|source=(\"$archive_name\")|" \
        -e "s|^sha256sums=.*|sha256sums=('$checksum')|" \
        -e "s|^_source_dir=.*|_source_dir=\"eitaas-linux-$version\"|" \
        "$build_dir/PKGBUILD"
    package_dir="$build_dir"
fi

cd "$package_dir"
makepkg --cleanbuild --force
mkdir -p "$project_root/dist"
find . -maxdepth 1 -type f -name '*.pkg.tar.*' -exec cp {} "$project_root/dist/" \;
